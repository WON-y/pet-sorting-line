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


# ---------- 색 모델 + 라벨 모델 (vision.model_mode: split) ----------
import pytest  # noqa: E402

from vision.bottle.classifier import COLOR_VALUES, LABEL_VALUES, combine, load_classifier, map_names, model_status  # noqa: E402


def test_combine_two_models_into_four_classes():
    assert combine("clear", 0.9, "nolabel", 0.8) == ("clear_nolabel", 0.8)   # 투명: 두 모델 중 낮은 값
    assert combine("clear", 0.9, "label", 0.95) == ("clear_label", 0.9)
    assert combine("color", 0.9, "label", 0.3) == ("color_label", 0.9)       # 유색: 라벨 모델과 상관없이 CO
    # 투명인데 라벨 모델이 확신 못 하면 재검사 (라벨 있는 병을 적합으로 통과시키지 않게)
    cls, conf = combine("clear", 0.99, "nolabel", 0.5)
    assert decide([(cls, conf)])[1] == "RE"
    cls, conf = combine("color", 0.99, "nolabel", 0.5)
    assert decide([(cls, conf)]) == ("color_nolabel", "CO")


def test_map_model_names():
    assert map_names({0: "clear", 1: "color"}, None, COLOR_VALUES) == {0: "clear", 1: "color"}
    assert map_names(["투명", "유색"], {"투명": "clear", "유색": "color"}, COLOR_VALUES) == {0: "clear", 1: "color"}
    with pytest.raises(ValueError):
        map_names({0: "with_label", 1: "no_label"}, None, LABEL_VALUES)       # 이름이 안 맞으면 바로 알림
    with pytest.raises(ValueError):
        map_names({0: "label", 1: "label"}, None, LABEL_VALUES)               # 한쪽 클래스가 없음


def test_missing_weights_reported_not_crash(tmp_path):
    vcfg = {"model_mode": "split", "color_model": {"weights": str(tmp_path / "c.pt")},
            "label_model": {"weights": str(tmp_path / "l.pt")}}
    assert "가중치 없음" in model_status(vcfg)
    with pytest.raises(FileNotFoundError):
        load_classifier(vcfg)


def test_runner_records_recheck_when_model_fails(tmp_path, monkeypatch):
    from app.controller import LineController
    from app.line import LineRunner
    from app.mock import MockVision
    from app.sim_belt import SimBelt

    belt = SimBelt()
    vision = MockVision(belt)

    def broken(_img):
        raise FileNotFoundError("색 모델 가중치가 없습니다")

    monkeypatch.setattr(vision, "classify", broken)
    msgs = []

    class Rec:
        def publish(self, topic, payload, retain=False):
            msgs.append((topic, payload))

    ctl = LineController(settle_ms=0)
    r = LineRunner({"app": {}, "vision": {}}, vision, belt, ctl, Rec(), capture_dir=tmp_path)
    r.execute(ctl.on_manual(0))
    r.execute(ctl.tick(0))
    j = [m for t, m in msgs if t == "pet/judgment"][0]
    assert j["code"] == "RE" and "img" in j                    # 사진은 남기고 재검사
    assert "가중치" in r.last_error
