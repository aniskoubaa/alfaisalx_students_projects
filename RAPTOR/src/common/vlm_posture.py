"""Ask the deployed VLM one question about one person, in the background.

"Is this person standing, sitting, or lying down? One word." Measured on the
bench (2026-09-29, Qwen3-VL-2B, crop scaled to 448 px): 0.41 s per answer, and it
called the seated person "sitting" where the keypoint rule of the first demo
said "standing". That is fast enough to re-check every person about once a
second without slowing the video: the camera loop never waits for it.

The model loads on this thread too, so the video window appears at once and the
HUD shows "VLM loading" for the ~7 s the weights take.

Known limit: with only an arm or a shoulder in view, the answer is a guess
(it said "standing" for a seated person cut off by the frame edge). Only crops
tall enough to show a body are sent (`min_height`).
"""
from __future__ import annotations

import threading
import time

QUESTION = ("Look at the main person in this image. Is the person standing, sitting, "
            "or lying down? Answer with exactly one word: standing, sitting, or lying.")
ANSWERS = ("standing", "sitting", "lying")


class VlmPosture:
    def __init__(self, model_dir, max_side=448, min_height=96):
        self.model_dir = str(model_dir)
        self.max_side, self.min_height = max_side, min_height
        self.state = "VLM loading"
        self.answers: dict[int, tuple[str, float, float]] = {}   # track id -> (word, when, seconds)
        self._job = None
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="vlm", daemon=True)
        self._thread.start()

    @property
    def ready(self):
        return self.state == "ready"

    @property
    def busy(self):
        with self._cond:
            return self._job is not None

    def submit(self, track_id, crop_bgr):
        """Queue one crop; ignored if a question is already in flight."""
        if crop_bgr is None or crop_bgr.shape[0] < self.min_height:
            return False
        with self._cond:
            if self._job is not None or not self.ready:
                return False
            self._job = (track_id, crop_bgr.copy())
            self._cond.notify()
            return True

    def answer(self, track_id, max_age=5.0):
        a = self.answers.get(track_id)
        if a and time.monotonic() - a[1] <= max_age:
            return a[0]
        return None

    def forget(self, live_ids):
        for k in [k for k in self.answers if k not in live_ids]:
            del self.answers[k]

    def _run(self):
        try:
            import cv2
            import torch
            from PIL import Image
            from transformers import AutoModelForImageTextToText, AutoProcessor

            proc = AutoProcessor.from_pretrained(self.model_dir)
            model = AutoModelForImageTextToText.from_pretrained(
                self.model_dir, dtype=torch.float16, device_map="cuda:0").eval()
            msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": QUESTION}]}]
            prompt = proc.apply_chat_template(msgs, add_generation_prompt=True)
        except Exception as e:  # noqa: BLE001 - the demo must keep running without it
            self.state = "VLM unavailable: {}".format(str(e)[:60])
            return

        def ask(crop):
            im = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            if max(im.size) > self.max_side:
                s = self.max_side / max(im.size)
                im = im.resize((max(1, int(im.size[0] * s)), max(1, int(im.size[1] * s))))
            inp = proc(text=prompt, images=[im], return_tensors="pt").to("cuda:0")
            with torch.no_grad():
                out = model.generate(**inp, max_new_tokens=4, do_sample=False, repetition_penalty=1.05)
            text = proc.batch_decode(out[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0]
            word = text.strip().lower()
            return next((a for a in ANSWERS if word.startswith(a)), "unclear")

        import numpy as np
        ask(np.zeros((224, 160, 3), dtype=np.uint8))   # warm-up: pays the sm_87 JIT once
        self.state = "ready"
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait_for(lambda: self._job is not None or self._stop.is_set())
                job = self._job
            if job is None:
                continue
            t0 = time.monotonic()
            try:
                word = ask(job[1])
                self.answers[job[0]] = (word, time.monotonic(), time.monotonic() - t0)
            except Exception as e:  # noqa: BLE001 - one bad crop must not end the checks
                self.last_error = str(e)[:80]
            with self._cond:
                self._job = None

    def stop(self, timeout=3.0):
        """Stop and wait for the answer in flight. False if the thread is still busy.

        Exiting while this thread is inside the model (mid-answer, or still
        loading) aborts the interpreter with "terminate called without an active
        exception" - seen on the board. An answer takes under a second, so
        waiting is enough; the caller must hard-exit if it is not.
        """
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        self._thread.join(timeout)
        return not self._thread.is_alive()
