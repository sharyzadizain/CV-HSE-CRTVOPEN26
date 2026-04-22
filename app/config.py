from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int, *, min_value: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    return value


def _float_env(name: str, default: float, *, min_value: float | None = None, max_value: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float") from exc
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    model_path: str = "yolov8n.pt"
    yolo_conf: float = 0.35
    yolo_imgsz: int = 640
    detect_every_n: int = 1
    preload_model: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_host=os.getenv("APP_HOST", "0.0.0.0"),
            app_port=_int_env("APP_PORT", 8000, min_value=1),
            model_path=os.getenv("MODEL_PATH", "yolov8n.pt"),
            yolo_conf=_float_env("YOLO_CONF", 0.35, min_value=0.01, max_value=1.0),
            yolo_imgsz=_int_env("YOLO_IMGSZ", 640, min_value=64),
            detect_every_n=_int_env("DETECT_EVERY_N", 1, min_value=1),
            preload_model=_bool_env("PRELOAD_MODEL", False),
        )

