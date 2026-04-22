from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import cv2
import numpy as np

from app.config import Settings


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    def to_payload(self, width: int, height: int) -> dict[str, Any]:
        x1 = max(0.0, min(float(width), self.x1))
        y1 = max(0.0, min(float(height), self.y1))
        x2 = max(0.0, min(float(width), self.x2))
        y2 = max(0.0, min(float(height), self.y2))
        return {
            "classId": self.class_id,
            "className": self.class_name,
            "confidence": round(float(self.confidence), 4),
            "bbox": {
                "x": round(x1 / width, 6) if width else 0.0,
                "y": round(y1 / height, 6) if height else 0.0,
                "w": round(max(0.0, x2 - x1) / width, 6) if width else 0.0,
                "h": round(max(0.0, y2 - y1) / height, 6) if height else 0.0,
            },
        }


class YoloDetector:
    def __init__(self, settings: Settings, model_factory: Callable[[str], Any] | None = None) -> None:
        self.settings = settings
        self._model_factory = model_factory or self._make_model
        self._model: Any | None = None
        self.names: dict[int, str] = {}

    @staticmethod
    def _make_model(model_path: str) -> Any:
        from ultralytics import YOLO

        model = YOLO(model_path)
        if hasattr(model, "to"):
            model.to("cpu")
        return model

    def load(self) -> Any:
        if self._model is None:
            self._model = self._model_factory(self.settings.model_path)
            raw_names = getattr(self._model, "names", {}) or {}
            self.names = {int(key): str(value) for key, value in dict(raw_names).items()}
        return self._model

    def predict(self, frame_bgr: np.ndarray) -> list[Detection]:
        model = self.load()
        results = model.predict(
            source=frame_bgr,
            conf=self.settings.yolo_conf,
            imgsz=self.settings.yolo_imgsz,
            device="cpu",
            verbose=False,
        )
        if not results:
            return []
        return self._parse_result(results[0], frame_bgr.shape[1], frame_bgr.shape[0])

    def _parse_result(self, result: Any, width: int, height: int) -> list[Detection]:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        xyxy = _as_numpy(getattr(boxes, "xyxy", []))
        confidences = _as_numpy(getattr(boxes, "conf", []))
        classes = _as_numpy(getattr(boxes, "cls", []))
        names = getattr(result, "names", None) or self.names

        detections: list[Detection] = []
        for coords, confidence, class_id in zip(xyxy, confidences, classes):
            cls_id = int(class_id)
            x1, y1, x2, y2 = [float(value) for value in coords[:4]]
            detections.append(
                Detection(
                    class_id=cls_id,
                    class_name=str(names.get(cls_id, f"class_{cls_id}")),
                    confidence=float(confidence),
                    x1=max(0.0, min(float(width), x1)),
                    y1=max(0.0, min(float(height), y1)),
                    x2=max(0.0, min(float(width), x2)),
                    y2=max(0.0, min(float(height), y2)),
                )
            )
        return detections


def draw_detections(frame_bgr: np.ndarray, detections: list[Detection]) -> np.ndarray:
    annotated = frame_bgr.copy()
    for detection in detections:
        x1, y1, x2, y2 = map(round, (detection.x1, detection.y1, detection.x2, detection.y2))
        color = _color_for_class(detection.class_id)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        label = f"{detection.class_name} {detection.confidence:.2f}"
        (label_w, label_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        label_y = max(label_h + baseline + 4, y1)
        cv2.rectangle(
            annotated,
            (x1, label_y - label_h - baseline - 6),
            (x1 + label_w + 8, label_y + baseline - 2),
            color,
            thickness=-1,
        )
        cv2.putText(
            annotated,
            label,
            (x1 + 4, label_y - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return annotated


def _as_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _color_for_class(class_id: int) -> tuple[int, int, int]:
    palette = (
        (52, 211, 153),
        (59, 130, 246),
        (245, 158, 11),
        (236, 72, 153),
        (14, 165, 233),
        (168, 85, 247),
        (239, 68, 68),
        (132, 204, 22),
    )
    return palette[class_id % len(palette)]

