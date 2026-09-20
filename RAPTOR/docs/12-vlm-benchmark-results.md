# 12 — VLM Benchmark Results (first round)

Measured on the flight computer, 2026-09-20. Raw rows:
[`results/vlm.jsonl`](../jetson_orin_nano_benchmarks/results/vlm.jsonl).
Full generations, for inspection:
[`gen_qwen25vl.json`](../jetson_orin_nano_benchmarks/results/gen_qwen25vl.json),
[`gen_smolvlm2.json`](../jetson_orin_nano_benchmarks/results/gen_smolvlm2.json).

This is a partial **E5** from [06](./06-benchmark-plan.md): two models, one serving
stack, bf16 only. **E6 (cue recall and hallucination rate) is not done** and cannot
be until the held-out staged-scene set exists.

## Conditions

| | |
|---|---|
| Board / power mode | Jetson Orin NX 16 GB, 25 W |
| Serving stack | `transformers` 5.17.0, bfloat16, greedy decoding |
| Prompt & schema | Verbatim from [03](./03-scene-understanding-vlm.md) |
| Input | 8 person crops from VisDrone, box expanded 30% for context |
| Cap | 160 new tokens |

**Crop sizes are generous.** Person heights were 115–385 px (median 198). The
optics table in [06](./06-benchmark-plan.md) puts a standing person at 64 px from
30 m and 48 px from 40 m, so these crops correspond to flying at roughly 10 m.
**Every quality observation below is therefore an upper bound.** At real search
altitude the models will see far less.

## Results

| | SmolVLM2-2.2B | **Qwen2.5-VL-3B** | Budget |
|---|---|---|---|
| Parameters | 2.25 B | 3.75 B | — |
| Model load | 9.9 s | 11.3 s | — |
| TTFT mean | 1.16 s | **0.67 s** | — |
| TTFT p95 | 1.41 s | **0.76 s** | ≤1.5 s ✔ (hard 3 s) |
| Full reply p95 (≈130 tok) | 11.5 s | 15.9 s | ≤5 s (hard 10 s) ✘ |
| Throughput | **14.3 tok/s** | 9.8 tok/s | — |
| **JSON parse rate** | **0 %** | **88 %** | — |
| **Schema-valid rate** | **0 %** | **88 %** | — |
| Peak GPU memory | **4.6 GB** | 7.2 GB | — |
| Power mean / max | 20.2 / **28.8 W** | **19.2** / 21.5 W | ≤20 W sustained, 25 W hard |

### On the latency budget

Both models exceed the full-reply budget as measured — but the measurement ran to
a 160-token cap, while [06](./06-benchmark-plan.md) budgets for a **~60-token**
description. Normalised to 60 tokens from the measured throughput (derived, not
directly measured):

| | 60-token estimate | Verdict |
|---|---|---|
| SmolVLM2 | 1.16 + 60/14.3 ≈ **5.4 s** | just over the 5 s target, inside the 10 s limit |
| Qwen2.5-VL-3B | 0.67 + 60/9.8 ≈ **6.8 s** | over target, inside the 10 s limit |

So the tier-3 budget is **achievable but tight** in plain `transformers` bf16 —
before any of the optimisations doc 03 assumes. INT4/AWQ quantisation and a faster
serving stack (llama.cpp, MLC, NanoLLM) are the obvious next levers, and doc 03
already names them. Neither model was quantised here.

## The finding that matters: SmolVLM2 invented demographics

SmolVLM2 produced **0 % schema-valid output**. It ignored the requested flat key
set, invented a deeper nested schema of its own, and ran past the token cap
mid-object — which is why nothing parsed.

Worse than the malformed JSON is *what* it invented. From an aerial crop:

```json
"appearance": {
    "gender": "female", "age": "20-29", "race": "Asian",
    "hair_color": "brown", "eye_color": "brown", "skin_tone": "dark",
    "body_type": "athletic"
}
```

**Eye colour is not visible from a drone.** Neither is race. The model was asked to
describe only what is visibly present and told to say "not visible" otherwise; it
instead produced confident demographic labelling of an identifiable person.

[08 — Limitations & safety](./08-limitations-and-safety.md) draws this as an
explicit design boundary:

> **No identity inference.** The system does not attempt face recognition,
> re-identification across flights, or demographic labelling of individuals. This
> is a design boundary, not an oversight — do not add it later "because it would
> be easy".

An unconstrained VLM will cross that boundary **by default**, unprompted, on the
first image you give it. Doc 08 also predicted the mechanism, in its failure table:
generative models "assert plausible detail that is not in the image — especially on
small, blurry crops".

Two conclusions:

1. **Grammar-constrained decoding is not an optimisation, it is a safety control.**
   Doc 03 already specifies it ("GBNF in llama.cpp, or the serving stack's JSON
   mode … makes this reliable rather than hopeful"). This measurement is the
   evidence: a fixed grammar would have made both the invented keys and the runaway
   generation impossible.
2. **Schema validation must reject unknown fields, not merely check the required
   ones.** A `race` key must be dropped on the floor by the validator, not
   forwarded to the operator because the other seven keys happened to be present.

The second generation shows the opposite failure of the same cause — the model
degenerating into filling its invented schema with `"unknown"` for twenty fields.

## Qwen2.5-VL-3B: better, with two caveats

Qwen produced valid, correctly-keyed JSON on 7 of 8 crops, stayed on observable
detail (clothing colour, posture, ground surface, nearby vehicles), and correctly
returned empty `injury_indicators` for ordinary pedestrians — it did not invent
injuries that were not there. That is the behaviour the design wants.

Two caveats worth recording:

- **`not_visible` came back empty every time.** From an oblique aerial crop the
  face is not visible, and usually neither is one side of the body. Doc 03 added
  that field precisely "to give the model a legitimate place to put uncertainty
  instead of inventing detail", and the model is not using it. It should be a
  prompt-engineering target, and possibly a validation rule — an aerial crop that
  claims *nothing* is unobservable is suspect on its face.
- **The 8th crop hit the token cap and failed to parse.** At 160 tokens the
  failure mode is truncation, not malformation. A grammar plus a slightly larger
  cap fixes it; without a grammar, 12 % of victim reports silently fail to parse.

### A grounding result, by accident

The harness sends a fixed context line — `posture=lying (geometric, conf 0.91);
immobile for 38 s` — with every crop, because in production that comes from tier 2.
The VisDrone crops show **standing** people, so that context was factually wrong
for all eight.

Both models reported the posture they *saw* (`standing`, `walking`) rather than
echoing the injected context. That is a genuinely reassuring grounding result: the
VLM is reading pixels, not paraphrasing the prompt. It is also a methodology bug on
my side — the context line should be derived per crop, and must be before E6 is
run, since a contradictory context is itself a hallucination trigger.

## Recommendation

**Qwen2.5-VL-3B-Instruct**, confirming the primary choice in
[03](./03-scene-understanding-vlm.md) — but on measured grounds rather than
reputation: 88 % vs 0 % schema validity, roughly half the time-to-first-token, and
lower peak and mean power, at the cost of 2.6 GB more memory and about 30 % lower
token throughput.

SmolVLM2 remains the right **low-memory fallback** for an 8 GB board, exactly as
doc 03 has it — but it must not be run without a decoding grammar.

Next, in order:

1. **Add grammar-constrained decoding** and re-measure schema validity. This is the
   highest-value change and it is a safety control, not a speed one.
2. **Quantise.** Neither model was quantised; doc 03 specifies INT4/AWQ. Expect the
   60-token reply to come comfortably inside budget.
3. **Try a faster serving stack** — llama.cpp with GBNF gives grammar and speed in
   one step.
4. **Build the E6 evaluation set** (~100 staged scenes, human-written references).
   Until it exists, the hallucination rate — the headline safety number for this
   tier — cannot be stated, and nothing here should be read as a quality score.
5. **Fix the per-crop context line** in `bench_vlm.py` before E6.
6. **Run E7 (contention).** The detector and VLM have never yet run at the same
   time, and at 7.2 GB peak plus the detector's engine, memory is no longer
   obviously free.
