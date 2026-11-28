"""병 사진 → 4클래스·신뢰도 (docs/spec/modes_and_states.md 4절).

판정 방식 (`vision.model_mode`)
- split (기본): **색 모델**(clear/color)과 **라벨 모델**(label/nolabel)을 따로 돌려 4클래스로 합친다.
- single: 예전 4클래스 모델 하나 (`vision.weights`).

합치는 규칙 (combine)
- 클래스 = "<색>_<라벨>" (예: clear + label → clear_label)
- 신뢰도: 유색이면 색 모델 신뢰도만 본다 (유색은 라벨과 상관없이 CO). 투명이면 두 모델 중 낮은 값.
  → 투명 병은 라벨 모델이 확신하지 못해도 재검사(RE)가 된다.

ultralytics는 모델을 불러올 때만 import 한다 (CI를 가볍게).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .preprocess import letterbox, prepare

COLOR_VALUES = ("clear", "color")
LABEL_VALUES = ("label", "nolabel")


def combine(color: str, color_conf: float, label: str, label_conf: float) -> tuple[str, float]:
    """색 모델·라벨 모델 결과 → (4클래스 이름, 판정에 쓰는 신뢰도)."""
    conf = color_conf if color == "color" else min(color_conf, label_conf)
    return f"{color}_{label}", conf


def map_names(model_names: dict | list, aliases: dict | None, allowed: tuple[str, ...]) -> dict[int, str]:
    """모델 클래스 번호 → 정해진 값. 모델 클래스 이름이 다르면 aliases({모델이름: 값})로 맞춘다.

    맞지 않는 클래스가 있으면 ValueError (잘못된 모델을 넣었을 때 바로 알 수 있게).
    """
    names = dict(enumerate(model_names)) if isinstance(model_names, list) else dict(model_names)
    aliases = aliases or {}
    out = {i: aliases.get(n, n) for i, n in names.items()}
    bad = sorted({v for v in out.values() if v not in allowed})
    if bad or set(out.values()) != set(allowed):
        raise ValueError(f"모델 클래스 {sorted(names.values())}를 {allowed}로 맞출 수 없습니다. "
                         f"settings.yaml의 names로 이름을 맞춰 주세요")
    return out


def _weights_path(path: str) -> Path:
    from common.config import ROOT

    p = Path(path)
    return p if p.is_absolute() else ROOT / p


class _YoloModel:
    def __init__(self, weights: str, imgsz: int, what: str):
        path = _weights_path(weights)
        if not path.is_file():
            raise FileNotFoundError(f"{what} 가중치가 없습니다: {weights}")
        from ultralytics import YOLO  # 무거운 import는 여기서

        self.model = YOLO(str(path))
        self.imgsz = imgsz

    def top1(self, img: Image.Image) -> tuple[int, float]:
        r = self.model.predict(img, imgsz=self.imgsz, verbose=False)[0]
        return int(r.probs.top1), float(r.probs.top1conf)


class SplitClassifier:
    """색 모델 + 라벨 모델."""

    def __init__(self, color_cfg: dict, label_cfg: dict, imgsz: int = 224, letterbox_color=(114, 114, 114)):
        self.imgsz, self.color_lb = imgsz, tuple(letterbox_color)
        self.color = _YoloModel(color_cfg["weights"], imgsz, "색 모델")
        self.label = _YoloModel(label_cfg["weights"], imgsz, "라벨 모델")
        self.color_names = map_names(self.color.model.names, color_cfg.get("names"), COLOR_VALUES)
        self.label_names = map_names(self.label.model.names, label_cfg.get("names"), LABEL_VALUES)

    def predict_image(self, bottle: Image.Image) -> tuple[str, float, dict]:
        img = letterbox(bottle, self.imgsz, self.color_lb)
        ci, cc = self.color.top1(img)
        li, lc = self.label.top1(img)
        color, label = self.color_names[ci], self.label_names[li]
        cls, conf = combine(color, cc, label, lc)
        return cls, conf, {"color": color, "color_conf": round(cc, 3), "label": label, "label_conf": round(lc, 3)}


class BottleClassifier:
    """예전 4클래스 모델 하나 (model_mode: single)."""

    def __init__(self, weights: str, roi=None, imgsz: int = 224, letterbox_color=(114, 114, 114)):
        self.yolo = _YoloModel(weights, imgsz, "4클래스 모델")
        self.model = self.yolo.model
        self.roi, self.imgsz, self.color = roi, imgsz, tuple(letterbox_color)

    def _run(self, img: Image.Image) -> tuple[str, float]:
        i, conf = self.yolo.top1(img)
        return self.model.names[i], conf

    def predict(self, frame_rgb) -> tuple[str, float]:
        """frame_rgb: numpy RGB 배열 (OpenCV는 BGR이므로 변환해서 넣기). 판정 구역(roi)을 잘라 판정."""
        return self._run(prepare(Image.fromarray(frame_rgb), self.roi, self.imgsz, self.color))

    def predict_image(self, bottle: Image.Image) -> tuple[str, float, dict]:
        """이미 잘라 낸 병 사진(preprocess.bottle_image)을 레터박스해서 판정."""
        cls, conf = self._run(letterbox(bottle, self.imgsz, self.color))
        return cls, conf, {}


def model_status(vcfg: dict) -> str:
    """대시보드 표시용: 어떤 모델을 쓰는지, 가중치 파일이 있는지 (모델은 불러오지 않음)."""
    if vcfg.get("model_mode", "split") == "single":
        ok = _weights_path(vcfg["weights"]).is_file()
        return "4클래스 모델" + ("" if ok else " (가중치 없음)")
    missing = [what for what, key in (("색", "color_model"), ("라벨", "label_model"))
               if not _weights_path(vcfg[key]["weights"]).is_file()]
    return "색 + 라벨 모델" + (f" ({'·'.join(missing)} 가중치 없음 → 모두 재검사)" if missing else "")


def load_classifier(vcfg: dict):
    """settings.yaml vision 설정으로 판정기를 만든다. predict_image(병 사진) → (클래스, 신뢰도, 세부)."""
    imgsz, lb = vcfg.get("imgsz", 224), vcfg.get("letterbox_color", (114, 114, 114))
    if vcfg.get("model_mode", "split") == "single":
        return BottleClassifier(vcfg["weights"], None, imgsz, lb)
    return SplitClassifier(vcfg["color_model"], vcfg["label_model"], imgsz, lb)
