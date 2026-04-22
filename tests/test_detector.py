import numpy as np

from app.config import Settings
from app.detector import Detection, YoloDetector, draw_detections


class FakeBoxes:
    xyxy = np.array([[10, 20, 60, 80]], dtype=np.float32)
    conf = np.array([0.91], dtype=np.float32)
    cls = np.array([0], dtype=np.float32)


class FakeResult:
    boxes = FakeBoxes()
    names = {0: "person"}


class FakeModel:
    names = {0: "person"}

    def __init__(self):
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        return [FakeResult()]


def test_yolo_detector_parses_detections_without_real_model():
    fake_model = FakeModel()
    detector = YoloDetector(Settings(model_path="fake.pt", yolo_conf=0.4, yolo_imgsz=320), lambda _: fake_model)

    frame = np.zeros((100, 120, 3), dtype=np.uint8)
    detections = detector.predict(frame)

    assert len(detections) == 1
    assert detections[0].class_name == "person"
    assert detections[0].confidence == np.float32(0.91)
    assert detections[0].to_payload(120, 100)["bbox"] == {
        "x": 0.083333,
        "y": 0.2,
        "w": 0.416667,
        "h": 0.6,
    }
    assert fake_model.calls[0]["device"] == "cpu"
    assert fake_model.calls[0]["conf"] == 0.4
    assert fake_model.calls[0]["imgsz"] == 320


def test_draw_detections_adds_pixels_and_preserves_input():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    detection = Detection(0, "person", 0.9, 10, 10, 50, 50)

    annotated = draw_detections(frame, [detection])

    assert annotated.sum() > 0
    assert frame.sum() == 0

