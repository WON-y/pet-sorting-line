"""웹 테스트용 인식기: 사진 한 장 → 상위 클래스 목록 (+ 4클래스 모델이면 판정 코드).

- `vision.weights`(학습한 4클래스 모델)가 있으면 그것을 쓰고, `vision/bottle`과 같은 전처리·판정 규칙을 쓴다.
- 없으면 `webtest.fallback_model`(ImageNet 기본 분류 모델)로 카메라·화면 연결만 시험한다. 이때 판정 코드는 없다.
- ultralytics는 사용할 때만 import 한다 (CI를 가볍게).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from PIL import Image

from common.protocol import CLASS_TO_CODE
from vision.bottle.decide import decide
from vision.bottle.preprocess import prepare

TOP_K = 5


def clamp_roi(roi, width: int, height: int):
    """사진 크기를 넘는 판정 구역은 잘라 맞춘다. 맞출 수 없으면 None (화면 전체)."""
    if not roi:
        return None
    x1, y1, x2, y2 = (int(v) for v in roi)
    x1, x2 = max(0, min(x1, width)), max(0, min(x2, width))
    y1, y2 = max(0, min(y1, height)), max(0, min(y2, height))
    return [x1, y1, x2, y2] if x2 > x1 and y2 > y1 else None


class Recognizer:
    """predict_topk(img) 하나만 있으면 되는 모델을 감싼다. 시험에서는 가짜 모델을 넣는다."""

    def __init__(self, model, model_name: str, vision_cfg: dict):
        self.model = model
        self.model_name = model_name
        self.roi = vision_cfg.get("roi")
        self.imgsz = int(vision_cfg["imgsz"])
        self.color = tuple(vision_cfg["letterbox_color"])
        self.conf_threshold = float(vision_cfg["conf_threshold"])
        self.classes = list(model.names)
        # 학습한 4클래스 모델인지: 클래스 이름이 규격(CLASS_TO_CODE)과 같아야 한다
        self.custom = set(self.classes) == set(CLASS_TO_CODE)
        self.lock = threading.Lock()  # 모델 하나를 여러 요청이 동시에 쓰지 않게

    def info(self) -> dict:
        return {
            "model": self.model_name,
            "custom": self.custom,
            "classes": self.classes if self.custom else [],   # 기본 모델은 1000개라 보내지 않음
            "num_classes": len(self.classes),
            "roi": self.roi,
            "conf_threshold": self.conf_threshold,
        }

    def predict(self, img: Image.Image, use_roi: bool = True) -> dict:
        img = img.convert("RGB")
        roi = clamp_roi(self.roi, img.width, img.height) if use_roi else None
        x = prepare(img, roi, self.imgsz, self.color)
        t0 = time.perf_counter()
        with self.lock:
            top = self.model.predict_topk(x, TOP_K)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        best_cls, best_conf = top[0] if top else ("", 0.0)
        result = {
            "top": [{"cls": c, "conf": round(p, 4)} for c, p in top],
            "cls": best_cls,
            "conf": round(best_conf, 4),
            "code": None,
            "roi": roi,
            "size": [img.width, img.height],
            "ms": ms,
        }
        if self.custom:
            # 실제 라인과 같은 규칙: 1프레임, 신뢰도 기준 미만이면 재검사(RE)
            result["code"] = decide([(best_cls, best_conf)], frames=1, conf_threshold=self.conf_threshold)[1]
        return result


class YoloTopK:
    """Ultralytics YOLO 분류 모델 → predict_topk 형태."""

    def __init__(self, weights: str, imgsz: int):
        from ultralytics import YOLO  # 무거운 import는 여기서

        self.yolo = YOLO(weights)
        if self.yolo.task != "classify":
            raise ValueError(f"분류(classify) 모델이 아닙니다: {weights} (task={self.yolo.task})")
        self.imgsz = imgsz
        self.names = [self.yolo.names[i] for i in sorted(self.yolo.names)]

    def predict_topk(self, img: Image.Image, k: int) -> list[tuple[str, float]]:
        r = self.yolo.predict(img, imgsz=self.imgsz, verbose=False)[0]
        probs = r.probs.data.tolist()
        order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)[:k]
        return [(self.names[i], float(probs[i])) for i in order]


def load_recognizer(settings: dict, root: Path, model_override: str | None = None) -> Recognizer:
    """설정대로 모델을 연다. 학습 가중치가 없으면 기본 모델로 대신한다."""
    vision_cfg = settings["vision"]
    if model_override:
        weights = model_override
    else:
        trained = root / vision_cfg["weights"]
        weights = str(trained) if trained.exists() else settings["webtest"]["fallback_model"]
    model = YoloTopK(weights, int(vision_cfg["imgsz"]))
    return Recognizer(model, Path(weights).name, vision_cfg)
