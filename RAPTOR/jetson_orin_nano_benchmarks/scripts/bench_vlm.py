#!/usr/bin/env python3
"""E5 — VLM sweep: time-to-first-token, throughput, memory, power, schema validity.

Implements the measurable half of 06-benchmark-plan.md's VLM experiments against
the prompt and JSON schema fixed in 03-scene-understanding-vlm.md.

    python3 bench_vlm.py --model ~/raptor-vlm/SmolVLM2-2.2B-Instruct \
        --crops ~/raptor-data/person-crops --max-new-tokens 160

What this does NOT measure: E6's cue-recall and hallucination rate. Those need
the held-out set of ~100 staged scenes with human-written reference descriptions,
which does not exist yet. Schema validity is measured; description *accuracy* is
not, and must not be inferred from these numbers.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import collect_env  # noqa: E402
from tegra_sampler import TegraSampler  # noqa: E402

# Verbatim from 03-scene-understanding-vlm.md: describe only what is visible,
# never diagnose, and give uncertainty a legitimate home in `not_visible`.
SYSTEM_PROMPT = (
    "You are a search-and-rescue vision assistant. Describe only what is visibly "
    "present in the image. If something is not clearly visible, say \"not visible\". "
    "Do not diagnose medical conditions. Do not speculate about causes."
)

USER_PROMPT = """Context: posture=lying (geometric, conf 0.91); immobile for 38 s;
camera altitude 32 m; oblique aerial view.

Describe this person. Reply with ONLY a JSON object with exactly these keys:
"appearance", "body_position", "surroundings", "injury_indicators" (list),
"signalling", "confidence", "not_visible" (list)."""

REQUIRED_KEYS = {"appearance", "body_position", "surroundings",
                 "injury_indicators", "signalling", "confidence", "not_visible"}


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a generation.

    Models wrap JSON in prose or fences even when told not to. The production
    system uses grammar-constrained decoding instead; this is the measurement
    equivalent, and the difference between 'valid' and 'recoverable' is itself
    a result worth having.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="local model directory")
    ap.add_argument("--crops", required=True, help="directory of person crops")
    ap.add_argument("--limit", type=int, default=8, help="crops to run")
    ap.add_argument("--max-new-tokens", type=int, default=160)
    ap.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--warmup", type=int, default=1, help="discarded generations")
    ap.add_argument("--board", default="orin-nx-16g")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=str(SCRIPT_DIR.parent / "results" / "vlm.jsonl"))
    ap.add_argument("--save-generations", help="write raw generations here for inspection")
    ap.add_argument("--no-tegrastats", action="store_true")
    args = ap.parse_args()

    import torch
    from PIL import Image
    from threading import Thread
    from transformers import AutoProcessor, AutoModelForImageTextToText, TextIteratorStreamer

    env = collect_env.collect(str(SCRIPT_DIR))
    dtype = getattr(torch, args.dtype)
    model_dir = Path(args.model)

    crops = sorted(p for p in Path(args.crops).iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[: args.limit]
    if not crops:
        raise SystemExit(f"no crops found in {args.crops}")

    print(f"loading {model_dir.name} ({args.dtype}) ...")
    t0 = time.perf_counter()
    processor = AutoProcessor.from_pretrained(str(model_dir))
    model = AutoModelForImageTextToText.from_pretrained(
        str(model_dir), dtype=dtype, device_map="cuda:0"
    )
    model.eval()
    load_s = time.perf_counter() - t0
    print(f"loaded in {load_s:.1f}s")

    params = sum(p.numel() for p in model.parameters())

    def build_inputs(image: Image.Image):
        messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "image"},
                                         {"type": "text", "text": USER_PROMPT}]},
        ]
        prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
        return processor(text=prompt, images=[image], return_tensors="pt").to("cuda:0")

    def generate(image: Image.Image) -> tuple[str, float, float, int]:
        """Return (text, ttft_s, total_s, new_token_count)."""
        inputs = build_inputs(image)
        streamer = TextIteratorStreamer(processor.tokenizer, skip_prompt=True,
                                        skip_special_tokens=True)
        kwargs = dict(**inputs, max_new_tokens=args.max_new_tokens,
                      do_sample=False, streamer=streamer)
        start = time.perf_counter()
        thread = Thread(target=model.generate, kwargs=kwargs)
        thread.start()

        chunks: list[str] = []
        ttft = float("nan")
        for chunk in streamer:
            if not chunks:
                ttft = time.perf_counter() - start
            chunks.append(chunk)
        thread.join()
        torch.cuda.synchronize()
        total = time.perf_counter() - start
        text = "".join(chunks)
        n_tokens = len(processor.tokenizer(text, add_special_tokens=False)["input_ids"])
        return text, ttft, total, n_tokens

    # Warm-up: first generation pays CUDA context, kernel autotune and, on this
    # board, PTX JIT for sm_87.
    for i in range(args.warmup):
        with Image.open(crops[0]) as im:
            generate(im.convert("RGB"))
        print(f"warm-up {i + 1}/{args.warmup} done")

    torch.cuda.reset_peak_memory_stats()
    sampler = None if args.no_tegrastats else TegraSampler()
    if sampler:
        sampler.start()

    ttfts: list[float] = []
    totals: list[float] = []
    tok_per_s: list[float] = []
    valid_json = 0
    schema_ok = 0
    generations: list[dict] = []

    for idx, crop in enumerate(crops):
        with Image.open(crop) as im:
            text, ttft, total, n_tok = generate(im.convert("RGB"))
        ttfts.append(ttft)
        totals.append(total)
        if total > 0 and n_tok:
            tok_per_s.append(n_tok / total)

        obj = extract_json(text)
        if obj is not None:
            valid_json += 1
            if REQUIRED_KEYS.issubset(obj.keys()):
                schema_ok += 1
        generations.append({"crop": crop.name, "ttft_s": round(ttft, 3),
                            "total_s": round(total, 3), "tokens": n_tok,
                            "json_parsed": obj is not None, "text": text})
        print(f"  [{idx + 1}/{len(crops)}] {crop.name}: ttft {ttft:.2f}s, "
              f"{total:.2f}s total, {n_tok} tok, json={'y' if obj else 'n'}")

    if sampler:
        sampler.stop()

    n = len(crops)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": "E5",
        "board": args.board,
        "model": model_dir.name,
        "model_path": str(model_dir),
        "params_b": round(params / 1e9, 2),
        "dtype": args.dtype,
        "serving_stack": "transformers",
        "crops": n,
        "max_new_tokens": args.max_new_tokens,
        "load_seconds": round(load_s, 2),
        "ttft_s": {"mean": round(statistics.fmean(ttfts), 3),
                   "p95": round(sorted(ttfts)[min(n - 1, int(0.95 * (n - 1)))], 3),
                   "max": round(max(ttfts), 3)},
        "total_s": {"mean": round(statistics.fmean(totals), 3),
                    "p95": round(sorted(totals)[min(n - 1, int(0.95 * (n - 1)))], 3),
                    "max": round(max(totals), 3)},
        "tokens_per_s_mean": round(statistics.fmean(tok_per_s), 2) if tok_per_s else None,
        "json_parse_rate": round(valid_json / n, 3),
        "schema_valid_rate": round(schema_ok / n, 3),
        "gpu_mem_peak_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "note": args.note,
        "env": env,
    }
    if sampler:
        row["tegrastats"] = sampler.summary()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    if args.save_generations:
        gen_path = Path(args.save_generations)
        gen_path.parent.mkdir(parents=True, exist_ok=True)
        gen_path.write_text(json.dumps(
            {"model": model_dir.name, "generations": generations}, indent=2), encoding="utf-8")

    print("\n--- result ---")
    print(f"model       {row['model']} ({row['params_b']}B, {row['dtype']})")
    print(f"load        {row['load_seconds']}s")
    print(f"ttft        mean {row['ttft_s']['mean']}s | p95 {row['ttft_s']['p95']}s  "
          f"(target <=1.5s, hard 3s)")
    print(f"full reply  mean {row['total_s']['mean']}s | p95 {row['total_s']['p95']}s  "
          f"(target <=5s, hard 10s)")
    print(f"throughput  {row['tokens_per_s_mean']} tok/s")
    print(f"json        parse {row['json_parse_rate']:.0%} | schema-valid {row['schema_valid_rate']:.0%}")
    print(f"gpu mem     {row['gpu_mem_peak_mb']} MB peak")
    ts = row.get("tegrastats") or {}
    if "board_power_mean_w" in ts:
        print(f"power       {ts['board_power_mean_w']} W mean / {ts['board_power_max_w']} W max")
    print(f"appended to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
