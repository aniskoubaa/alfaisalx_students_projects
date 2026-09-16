# 03 — Scene Understanding: which "LLM", and why

## First, a correction of terms that matters

We do not want an **LLM**. We want a **VLM** (vision-language model, also called a
multimodal LLM). A text-only LLM cannot see the camera feed; the best it could do is
paraphrase YOLO's class labels — turning `person, 0.87, lying` into "a person is
lying down", which adds nothing and can only introduce error.

Everything that makes this project interesting — *"dark staining on the right
trouser leg"*, *"arm bent at an unnatural angle"*, *"waving at the camera"*,
*"trapped under debris"* — lives in pixels that YOLO does not describe. That requires
a model that takes the image itself as input.

## Decision summary

| Role | Choice |
|------|--------|
| **Primary** | **Qwen2.5-VL-3B-Instruct**, INT4/AWQ quantised |
| **Jetson-native fallback** | **VILA-1.5-3B** via NVIDIA `NanoLLM` / `jetson-containers` |
| **Low-memory fallback (8 GB board)** | **SmolVLM2** (Apache-2.0) or **Moondream2** |
| **Fast caption tier (optional)** | **Florence-2-base** (MIT) for a cheap one-line caption on every track |
| **Explicitly rejected** | Any cloud API model (GPT-4o, Claude, Gemini) as a flight-critical component |

## Why Qwen2.5-VL-3B

- **It fits.** At 4-bit it is roughly 2–2.5 GB of weights plus activations and KV
  cache — comfortable on a 16 GB Orin NX alongside TensorRT engines and ROS 2.
- **Strongest small VLM in its class** for fine-grained visual detail, which is exactly
  what injury cues need: it is better than similarly sized models at "describe the
  specific visual state of this region".
- **Real grounding ability** — it can be asked about a specific region and can return
  coordinates, so we can point it at *our* detected person rather than hoping it picks
  the right one in a crowded frame.
- **Native dynamic resolution.** It handles our variable-size person crops without us
  destroying detail by squashing everything to a fixed 336x336. For small aerial
  subjects this is a real accuracy difference, not a nicety.
- **Well-supported quantisation path** — AWQ/GPTQ int4 checkpoints exist and it is
  supported by the common serving stacks.

**Check the licence on the exact checkpoint before we commit.** The Qwen2.5-VL family
is not uniformly licensed — some sizes are Apache-2.0 and some ship under a Qwen
research/community licence with use restrictions. Verify the specific 3B checkpoint's
`LICENSE` file; if it is research-only and that conflicts with our goals, drop to
**Qwen2-VL-2B (Apache-2.0)** or **SmolVLM2 (Apache-2.0)**, both of which are acceptable.

## Why the alternatives lost

| Model | Verdict |
|-------|---------|
| **GPT-4o / Claude / Gemini via API** | Would give the best descriptions by a wide margin — and is useless to us. Disaster areas do not have reliable connectivity, round-trip latency over a degraded link is unpredictable, and the drone must not depend on a link to do its job. **However:** keep an optional *ground-station-side* enrichment path. When a link exists, the GCS can re-query a frontier model on the saved snapshot for a second opinion. Onboard autonomy, opportunistic cloud quality. |
| **VILA-1.5-3B** | Genuinely good, and NVIDIA optimises it specifically for Jetson (NanoLLM, quantised, multi-image). Marginally behind Qwen2.5-VL on fine detail. **Keep as fallback #1** — if Qwen's deployment path fights us on JetPack, VILA is the path of least resistance. |
| **LLaVA-1.5 / 1.6 (7B)** | The classic, lots of tutorials. Rejected: 7B is a heavy lift for our memory budget, and a 2024-era 7B is now matched by a 2025-era 3B. Poor size/quality trade. |
| **SmolVLM2** | Apache-2.0, extremely fast, tiny memory. Descriptions are noticeably shallower. **This is the 8 GB-board answer**, and the right choice if we ever need the VLM to run several times per second. |
| **Moondream2 (~1.8B)** | Punches above its weight at VQA, permissively licensed, easy to run. Good fallback; weaker on fine-grained detail than Qwen. |
| **Florence-2 (MIT)** | Not an instruction-following chat model — it does captioning, detection and grounding via task tokens, so it cannot be asked open questions about injury. But it is *fast*, and a "detailed caption" on every new track for pennies of compute is a genuinely useful cheap intermediate tier. **Optional add-on, not the main model.** |
| **PaliGemma 2** | Strong, but designed to be fine-tuned per task rather than prompted zero-shot; Gemma licence terms need review. Revisit only if we decide to fine-tune a VLM (see below — we probably should not). |
| **Fine-tuning our own VLM** | See [05](./05-custom-models-and-data.md). Short answer: no, not at this stage. Prompt engineering plus a structured output schema gets us most of the way, and we do not have the labelled data to do better. |

## The critical design decision: the VLM is event-triggered

A 3B VLM on an Orin NX will produce something in the range of **tens of tokens per
second**, with image prefill on top. A 60-token description therefore costs on the
order of **2-6 seconds**. (Firm numbers are a benchmark deliverable, not an assumption
— see [06](./06-benchmark-plan.md).)

That is fine, because we never run it per frame. We run it when tiers 1-2 say it is
worth it:

```python
def should_describe(track) -> bool:
    if track.is_new and track.frames_confirmed >= 15:      # a genuinely new person
        return True
    if track.posture in {"lying", "crouching"} and not track.described_posture_state:
        return True                                        # posture became alarming
    if track.immobile_seconds > 20 and track.age_since_vlm > 60:
        return True                                        # still not moving
    if track.operator_requested:                           # a human asked
        return True
    if track.age_since_vlm > 120:                          # periodic refresh
        return True
    return False
```

Jobs go into a **bounded priority queue** (depth ~4, most-alarming-first). If the queue
is full we drop low-priority refreshes, never new-person or posture-change events. The
detector never blocks on this.

## Prompting: ground the model, constrain the output

Two rules.

**1. Give the VLM the crop, plus what we already know.** Never send the raw full frame
and hope. Send the tracked person's bounding box expanded ~30% for context, plus
structured facts from tiers 1-2:

```
System: You are a search-and-rescue vision assistant. Describe only what is visibly
present in the image. If something is not clearly visible, say "not visible". Do not
diagnose medical conditions. Do not speculate about causes.

Image:   <crop of person 7, 30% context margin>
Context: posture=lying (geometric, conf 0.91); immobile for 38 s;
         camera altitude 32 m; oblique view; time 14:02 local.

Report:
1. Appearance: clothing colour, approximate adult/child, anything carried.
2. Body position: limb positions, anything unnatural about the geometry.
3. Surroundings: surface, debris, vehicles, hazards, other people.
4. Visible signs of distress or injury (e.g. staining, wounds, entrapment),
   or "none visible".
5. Any deliberate movement or signalling.
```

**2. Force structured output.** Free text is unparseable and invites rambling. Have the
VLM emit JSON against a fixed schema and validate it:

```json
{
  "appearance": "adult, light shirt, dark trousers",
  "body_position": "prone, left arm extended above head",
  "surroundings": "gravel, near a low wall, no other people",
  "injury_indicators": ["dark staining on right lower leg"],
  "signalling": "none observed",
  "confidence": "medium",
  "not_visible": ["face", "right arm"]
}
```

Constrained / grammar-based decoding (GBNF in llama.cpp, or the serving stack's JSON
mode) makes this reliable rather than hopeful. The `not_visible` field is deliberate —
it gives the model a legitimate place to put uncertainty instead of inventing detail.

## Serving stack — to be decided by measurement

Candidates, in rough order of "likely to work on JetPack 6 without a fight":

1. **`jetson-containers` + NanoLLM** (NVIDIA / dusty-nv) — built for exactly this board.
   Easiest path, especially for VILA.
2. **llama.cpp / GGUF** with the multimodal projector — very portable, CUDA-accelerated,
   GBNF grammars give us the JSON schema for free. Usually the pragmatic winner.
3. **MLC-LLM** — strong quantised throughput on Jetson, more setup effort.
4. **TensorRT-LLM** — fastest ceiling, highest integration cost, weakest VLM coverage.
5. **vLLM** — excellent server, but built for datacentre GPUs; Jetson is not its happy path.

Benchmark 1 and 2 first. Pick on measured tokens/s, time-to-first-token, and peak
memory — see [06](./06-benchmark-plan.md).

## What the VLM must never do

It produces **observations**, not **conclusions**. It is not permitted to output a
triage category, a medical assessment, or a "this person is dead or alive" judgement,
and we will not prompt it to. The `triage_flag` in the victim report is computed by
explicit, auditable rules over the structured fields (posture + immobility duration +
presence of injury indicators), so a human can see exactly why something was flagged.
See [08 — Limitations & safety](./08-limitations-and-safety.md).
