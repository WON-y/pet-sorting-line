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


def crop_box(img: Image.Image, box: tuple[int, int, int, int], margin: float = 0.2) -> Image.Image:
    """감지한 병 박스(x, y, w, h)를 가운데 둔 정사각형으로 자른다. 여백은 병 긴 변 대비 비율.

    학습용 온라인 사진(병 둘레를 자른 사진)과 비슷한 구도를 만들기 위해 쓴다. 화면 밖은 잘라 낸다.
    """
    x, y, w, h = box
    side = max(w, h) * (1 + 2 * margin)
    cx, cy = x + w / 2, y + h / 2
    x1, y1 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x2, y2 = int(min(img.width, cx + side / 2)), int(min(img.height, cy + side / 2))
    return img.crop((x1, y1, max(x1 + 1, x2), max(y1 + 1, y2)))


def bottle_image(img: Image.Image, box=None, roi=None, mode: str = "box", margin: float = 0.2) -> Image.Image:
    """판정·저장에 쓸 병 사진 (레터박스 전). mode가 box이고 박스가 있으면 병 둘레, 아니면 판정 구역."""
    if mode == "box" and box is not None:
        return crop_box(img, box, margin)
    return crop_roi(img, roi)
