"""Lean TensorRT runner for the RT-DETRv4 engine (the Apache-2.0 aerial detector).

Same call as trt_yolo.TrtYolo, so the live demo can use either:

    from trt_rtdetr import TrtRtdetr
    det = TrtRtdetr("~/raptor-deploy/detector_alt/visdrone-rtdetrv4-s.engine",
                    classes=[0, 1], conf=0.35)          # VisDrone: pedestrian + people
    boxes, scores = det(frame_bgr)                      # xyxy pixels in the frame

The engine is the one bench_rtdetrv4.py builds: the model with its own
post-processor inside, inputs `images` [1,3,H,W] and `orig_target_sizes` [1,2],
outputs `labels`, `boxes` (already in frame pixels) and `scores` - so there is no
NMS here. Pre-processing is exactly the benchmark's: a plain resize to the input
size (not a letterbox), BGR->RGB, 0-1.

Unlike an Ultralytics engine there is no JSON metadata header in front of the
serialized engine - which is how the demo tells the two kinds apart.
"""
from __future__ import annotations

from pathlib import Path


class TrtRtdetr:
    def __init__(self, engine_path, classes=None, conf=0.35):
        import tensorrt as trt
        import torch

        self.torch = torch
        path = Path(engine_path).expanduser()
        self.engine = trt.Runtime(trt.Logger(trt.Logger.WARNING)).deserialize_cuda_engine(path.read_bytes())
        if self.engine is None:
            raise RuntimeError(f"TensorRT could not load {path} (built by another TensorRT/GPU?)")
        self.ctx = self.engine.create_execution_context()
        self.stream = torch.cuda.Stream()
        dtypes = {trt.float32: torch.float32, trt.float16: torch.float16,
                  trt.int32: torch.int32, trt.int64: torch.int64}
        self.buf = {}
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            t = torch.empty(tuple(self.engine.get_tensor_shape(name)),
                            dtype=dtypes[self.engine.get_tensor_dtype(name)], device="cuda")
            self.buf[name] = t
            self.ctx.set_tensor_address(name, t.data_ptr())
        self.h, self.w = self.buf["images"].shape[2], self.buf["images"].shape[3]
        self.keep = torch.tensor(list(classes) if classes else [], device="cuda")
        self.conf = conf

    def __call__(self, frame_bgr, conf=None):
        """BGR frame -> (boxes xyxy [N,4], scores [N]) as numpy, in frame pixels."""
        import cv2

        torch = self.torch
        oh, ow = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(frame_bgr, (self.w, self.h), interpolation=cv2.INTER_LINEAR),
                           cv2.COLOR_BGR2RGB)
        with torch.cuda.stream(self.stream):
            x = torch.from_numpy(rgb).cuda(non_blocking=True).permute(2, 0, 1)[None].float().div_(255)
            self.buf["images"].copy_(x)
            self.buf["orig_target_sizes"].copy_(
                torch.tensor([[ow, oh]], device="cuda").to(self.buf["orig_target_sizes"].dtype))
            if not self.ctx.execute_async_v3(self.stream.cuda_stream):
                raise RuntimeError("TensorRT execution failed")
        self.stream.synchronize()
        labels, boxes, scores = self.buf["labels"][0], self.buf["boxes"][0], self.buf["scores"][0]
        sel = scores > (self.conf if conf is None else conf)
        if len(self.keep):
            sel &= torch.isin(labels, self.keep.to(labels.dtype))
        b = boxes[sel].float()
        b[:, [0, 2]] = b[:, [0, 2]].clamp(0, ow)
        b[:, [1, 3]] = b[:, [1, 3]].clamp(0, oh)
        return b.cpu().numpy(), scores[sel].float().cpu().numpy()
