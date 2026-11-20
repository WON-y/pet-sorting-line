"""학습과 판정이 함께 쓰는 전처리 (docs/spec/data_and_logging.md 4절).

이 파일의 함수를 학습 노트북에서도 그대로 써야 한다. 다르면 판정 정확도가 떨어진다.
"""
from __future__ import annotations

from PIL import Image


def crop_roi(img: Image.Image, roi: list[int] | tuple[int, int, int, int] | None) -> Image.Image:
    """판정 구역만 자른다. roi가 None이면 그대로."""
    return img.crop(tuple(roi)) if roi else img


def letterbox(img: Image.Image, size: int = 224, color: tuple[int, int, int] = (114, 114, 114)) -> Image.Image:
    """비율을 유지해 size×size에 맞추고 남는 곳을 회색으로 채운다."""
    img = img.convert("RGB")
    w, h = img.size
    scale = size / max(w, h)
    new = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), tuple(color))
    canvas.paste(new, ((size - new.width) // 2, (size - new.height) // 2))
    return canvas


def prepare(img: Image.Image, roi=None, size: int = 224, color=(114, 114, 114)) -> Image.Image:
    return letterbox(crop_roi(img, roi), size, tuple(color))
