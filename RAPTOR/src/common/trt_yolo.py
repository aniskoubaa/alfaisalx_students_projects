"""Lean TensorRT runner for Ultralytics-exported YOLO detection engines.

Why this exists: Ultralytics' Python pipeline (letterbox, result objects, plotting
helpers) costs 15-20 ms per frame on this board - more than the network itself
(docs/10, "GPU-only timing"). This runs the same .engine file directly: resize and
pad exactly as Ultralytics does, one TensorRT call, then filtering and NMS on the
GPU. Accuracy is identical by construction; check it with bench_lean_yolo.py.

    from trt_yolo import TrtYolo
    det = TrtYolo("~/raptor-deploy/detector/visdrone-yolo26s-736x1280.engine",
                  classes=[0, 1], conf=0.35)       # VisDrone: pedestrian + people
    boxes, scores = det(frame_bgr)                  # xyxy pixels in the frame

The engine file is Ultralytics' format: a 4-byte length, a JSON metadata block
(input size, class names), then the serialized TensorRT engine. The exported
detectors here have no NMS inside (output [1, 4 + classes, anchors]), so it is
done here: the chosen classes are merged into one "person" score and a single
class-agnostic NMS removes duplicates - the same rule person_scoring.py uses.
"""
from __future__ import annotations

import json
from pathlib import Path


class TrtYolo:
    """`gpu_preprocess=True` uploads the raw frame and does the resize, padding and
    BGR->RGB on the GPU instead of cv2. Measured 2026-10-05 on 150 real 1080p
    frames (tests/check_trt_yolo_gpu.py): 19.8 ms vs 21.2 ms per call, only 1.07x
    faster - the CPU resize was NOT the bottleneck docs/STATUS assumed - and the
    person count differed on 12.7 % of frames (borderline boxes near the threshold
    flip on sub-pixel differences; matched boxes agree at IoU 0.992). So the CPU
    path stays the default. Kept as an option for much larger inputs (4K), where
    the CPU resize costs four times as much; re-check before switching."""

    def __init__(self, engine_path, classes=None, conf=0.25, iou=0.7, max_det=300, gpu_preprocess=False):
        import numpy as np  # noqa: F401 - imported for the caller's convenience
        import tensorrt as trt
        import torch

        self.torch = torch
        path = Path(engine_path).expanduser()
        with path.open("rb") as fh:
            n = int.from_bytes(fh.read(4), byteorder="little", signed=True)
            self.meta = json.loads(fh.read(n).decode("utf-8"))
            blob = fh.read()
        self.engine = trt.Runtime(trt.Logger(trt.Logger.WARNING)).deserialize_cuda_engine(blob)
        if self.engine is None:
            raise RuntimeError(f"TensorRT could not load {path} (built by another TensorRT/GPU?)")
        self.ctx = self.engine.create_execution_context()
        self.stream = torch.cuda.Stream()
        dtypes = {trt.float32: torch.float32, trt.float16: torch.float16}
        self.buf = {}
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            shape = tuple(self.engine.get_tensor_shape(name))
            t = torch.empty(shape, dtype=dtypes[self.engine.get_tensor_dtype(name)], device="cuda")
            self.buf[name] = t
            self.ctx.set_tensor_address(name, t.data_ptr())
            if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                self.inp = name
            else:
                self.out = name
        self.h, self.w = self.buf[self.inp].shape[2], self.buf[self.inp].shape[3]
        self.names = {int(k): v for k, v in (self.meta.get("names") or {}).items()}
        self.classes = list(classes) if classes else None
        self.conf, self.iou, self.max_det = conf, iou, max_det
        self.gpu_preprocess = gpu_preprocess

    def letterbox(self, frame):
        """Ultralytics LetterBox(auto=False, center=True, pad 114) - same pixels in."""
        import cv2

        h0, w0 = frame.shape[:2]
        r = min(self.h / h0, self.w / w0)
        nw, nh = int(round(w0 * r)), int(round(h0 * r))
        dw, dh = (self.w - nw) / 2, (self.h - nh) / 2
        img = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR) if (nw, nh) != (w0, h0) else frame
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        return img, r, left, top

    def _letterbox_gpu(self, frame_bgr):
        """The same letterbox as letterbox(), done on the GPU, written straight into
        the engine's input buffer. Returns (r, pad_x, pad_y). Call on self.stream."""
        torch = self.torch
        import torch.nn.functional as F

        h0, w0 = frame_bgr.shape[:2]
        r = min(self.h / h0, self.w / w0)
        nw, nh = int(round(w0 * r)), int(round(h0 * r))
        dw, dh = (self.w - nw) / 2, (self.h - nh) / 2
        top, left = int(round(dh - 0.1)), int(round(dw - 0.1))
        x = torch.from_numpy(frame_bgr).cuda(non_blocking=True)          # HWC uint8, BGR
        x = x.permute(2, 0, 1)[None].float()
        if (nw, nh) != (w0, h0):
            x = F.interpolate(x, size=(nh, nw), mode="bilinear", align_corners=False)
        inp = self.buf[self.inp]
        inp.fill_(114.0 / 255.0)                                          # Ultralytics' grey padding
        inp[:, :, top:top + nh, left:left + nw] = x[:, [2, 1, 0]].round_().div_(255.0)   # ->RGB, 0-1
        return r, left, top

    def __call__(self, frame_bgr, conf=None):
        """BGR frame -> (boxes xyxy [N,4], scores [N]) as numpy, in frame pixels."""
        torch = self.torch
        from torchvision.ops import nms

        # Everything on the one stream TensorRT runs on: the input copy and the
        # inference must be ordered, or TensorRT can read a half-written input.
        if self.gpu_preprocess:
            with torch.cuda.stream(self.stream):
                r, px, py = self._letterbox_gpu(frame_bgr)
                if not self.ctx.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError("TensorRT execution failed")
        else:
            img, r, px, py = self.letterbox(frame_bgr)
            with torch.cuda.stream(self.stream):
                x = torch.from_numpy(img).cuda(non_blocking=True)
                x = x[..., [2, 1, 0]].permute(2, 0, 1)[None].float().div_(255)   # BGR->RGB, CHW, 0-1
                self.buf[self.inp].copy_(x)
                if not self.ctx.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError("TensorRT execution failed")
        self.stream.synchronize()

        out = self.buf[self.out][0]                     # [4 + classes, anchors]
        box, cls = out[:4], out[4:]
        cls = cls[self.classes] if self.classes else cls
        score = cls.max(0).values                       # merged "person" score
        keep = score > (self.conf if conf is None else conf)
        if not keep.any():
            return (torch.zeros((0, 4)).numpy(), torch.zeros(0).numpy())
        b, s = box[:, keep].T, score[keep]
        xyxy = torch.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2,
                            b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2], 1)
        k = nms(xyxy, s, self.iou)[: self.max_det]
        xyxy, s = xyxy[k], s[k]
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - px) / r   # undo the letterbox
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - py) / r
        h0, w0 = frame_bgr.shape[:2]
        xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clamp(0, w0)
        xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clamp(0, h0)
        return xyxy.float().cpu().numpy(), s.float().cpu().numpy()
