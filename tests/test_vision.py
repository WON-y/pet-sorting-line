"""전처리·확정 규칙·손짓 확정 (모델 없이)."""
from PIL import Image

from vision.bottle.decide import decide
from vision.bottle.preprocess import crop_roi, letterbox
from vision.gesture.gesture import GestureConfirmer


def test_letterbox_keeps_ratio_and_pads_gray():
    img = Image.new("RGB", (400, 200), (255, 0, 0))
    out = letterbox(img, 224, (114, 114, 114))
    assert out.size == (224, 224)
    assert out.getpixel((112, 2)) == (114, 114, 114)   # 위쪽 여백
    assert out.getpixel((112, 112)) == (255, 0, 0)     # 가운데는 원본


def test_crop_roi():
    img = Image.new("RGB", (640, 480))
    assert crop_roi(img, [100, 50, 300, 250]).size == (200, 200)
    assert crop_roi(img, None).size == (640, 480)


def test_decide_single_frame():
    # 기본: 벨트 정지 후 1프레임 판정 (vision.frames: 1)
    assert decide([("clear_nolabel", 0.9)]) == ("clear_nolabel", "OK")
    assert decide([("clear_label", 0.9)]) == ("clear_label", "NG")
    assert decide([("color_label", 0.9)]) == ("color_label", "CO")      # 유색은 라벨과 상관없이 CO
    assert decide([("color_nolabel", 0.9)]) == ("color_nolabel", "CO")
    assert decide([("clear_nolabel", 0.59)])[1] == "RE"                 # 신뢰도 < 0.6 → 재검사
    assert decide([("clear_nolabel", 0.6)])[1] == "OK"                  # 기준과 같으면 통과
    assert decide([])[1] == "RE"                                       # 프레임 없음
    assert decide([("clear_content", 0.9)])[1] == "RE"                  # 규격에서 뺀 클래스


def test_decide_multi_frame_still_supported():
    assert decide([("clear_label", 0.9)] * 3, frames=3) == ("clear_label", "NG")
    assert decide([("clear_label", 0.9), ("clear_label", 0.9), ("clear_nolabel", 0.9)], frames=3)[1] == "RE"
    assert decide([("clear_nolabel", 0.9), ("clear_nolabel", 0.5), ("clear_nolabel", 0.9)], frames=3)[1] == "RE"
    assert decide([("clear_nolabel", 0.9)] * 2, frames=3)[1] == "RE"   # 프레임 부족


def test_gesture_needs_consecutive_frames():
    g = GestureConfirmer(confirm_frames=3)
    assert [g.update(2) for _ in range(3)] == [None, None, 2]
    assert g.update(2) is None            # 같은 손짓은 한 번만 확정
    assert [g.update(3) for _ in range(3)] == [None, None, None]   # 3개는 규칙에 없음
