"""웹캠 프레임 → 클래스·신뢰도. ultralytics는 사용할 때만 import 한다 (CI를 가볍게)."""
from __future__ import annotations

from PIL import Image

from .preprocess import prepare


class BottleClassifier:
    def __init__(self, weights: str, roi=None, imgsz: int = 224, letterbox_color=(114, 114, 114)):
        from ultralytics import YOLO  # 무거운 import는 여기서

        self.model = YOLO(weights)
        self.roi, self.imgsz, self.color = roi, imgsz, tuple(letterbox_color)

    def predict(self, frame_rgb) -> tuple[str, float]:
        """frame_rgb: numpy RGB 배열 (OpenCV는 BGR이므로 변환해서 넣기)."""
        img = prepare(Image.fromarray(frame_rgb), self.roi, self.imgsz, self.color)
        r = self.model.predict(img, imgsz=self.imgsz, verbose=False)[0]
        return self.model.names[int(r.probs.top1)], float(r.probs.top1conf)
