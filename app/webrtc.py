from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from fractions import Fraction
from typing import Any

import numpy as np
from aiortc import MediaStreamTrack
from av import VideoFrame

from app.detector import Detection, YoloDetector, draw_detections


LOGGER = logging.getLogger("webrtc-yolo")


class YoloVideoTransformTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, track: MediaStreamTrack, detector: YoloDetector, detect_every_n: int = 1) -> None:
        super().__init__()
        self.track = track
        self.detector = detector
        self.detect_every_n = max(1, detect_every_n)
        self.frame_id = 0
        self._latest_detections: list[Detection] = []
        self._latest_inference_ms = 0.0
        self._data_channel: Any | None = None
        self._frame_times: deque[float] = deque(maxlen=30)
        self._pending_detection: asyncio.Task[tuple[list[Detection], float]] | None = None

    def set_data_channel(self, channel: Any) -> None:
        self._data_channel = channel

    async def recv(self) -> VideoFrame:
        frame = await self.track.recv()
        self.frame_id += 1

        image = frame.to_ndarray(format="bgr24")
        height, width = image.shape[:2]

        self._consume_detection_result()
        self._schedule_detection(image)

        annotated = draw_detections(image, self._latest_detections)
        self._send_detections(width, height)

        new_frame = VideoFrame.from_ndarray(annotated, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base or Fraction(1, 90000)
        return new_frame

    def stop(self) -> None:
        if self._pending_detection is not None:
            self._pending_detection.cancel()
            self._pending_detection = None
        super().stop()

    def _consume_detection_result(self) -> None:
        task = self._pending_detection
        if task is None or not task.done():
            return

        self._pending_detection = None
        try:
            detections, inference_ms = task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("YOLO inference failed")
            self._latest_detections = []
            self._latest_inference_ms = 0.0
            return

        self._latest_detections = detections
        self._latest_inference_ms = inference_ms

    def _schedule_detection(self, image: np.ndarray) -> None:
        if self._pending_detection is not None:
            return
        if self.frame_id != 1 and self.frame_id % self.detect_every_n != 0:
            return

        frame_copy = image.copy()
        self._pending_detection = asyncio.create_task(self._detect(frame_copy))

    async def _detect(self, image: np.ndarray) -> tuple[list[Detection], float]:
        started = time.perf_counter()
        detections = await asyncio.to_thread(self.detector.predict, image)
        inference_ms = (time.perf_counter() - started) * 1000.0
        return detections, inference_ms

    def _send_detections(self, width: int, height: int) -> None:
        now = time.time()
        self._frame_times.append(now)
        fps = 0.0
        if len(self._frame_times) > 1:
            elapsed = self._frame_times[-1] - self._frame_times[0]
            if elapsed > 0:
                fps = (len(self._frame_times) - 1) / elapsed

        payload = {
            "type": "detections",
            "frameId": self.frame_id,
            "timestamp": now,
            "fps": round(fps, 2),
            "inferenceMs": round(self._latest_inference_ms, 2),
            "detections": [detection.to_payload(width, height) for detection in self._latest_detections],
        }
        channel = self._data_channel
        if channel is not None and getattr(channel, "readyState", None) == "open":
            channel.send(json.dumps(payload, separators=(",", ":")))
