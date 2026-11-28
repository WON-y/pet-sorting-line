"""가상 벨트·도착 감지·실행기 (하드웨어·웹캠·모델 없이)."""
import pytest

from app.controller import LineController
from app.line import LineRunner
from app.mock import MockVision
from app.sim_belt import SimBelt
from vision.bottle.detect import StreakCounter, box_inside
from vision.bottle.preprocess import bottle_image, crop_box

# ---------- 가상 벨트: 우노 펌웨어와 같은 규칙 ----------


def test_sim_belt_starts_latched_and_needs_reset_in_mode_1_or_2():
    b = SimBelt(mode=3)
    assert b.run == "STOP" and b.read_lines() == ["EVT,STOP,POWERON"]
    assert b.press_reset() == "MODE_NOT_1_OR_2" and b.run == "STOP"
    b.set_mode(1)
    assert b.run == "STOP"                       # 모드만 바꿔서는 출발하지 않음
    assert b.press_reset() == "OK" and b.run == "RUN"


def test_sim_belt_pause_go_and_stops():
    b = SimBelt()
    b.press_reset()
    b.read_lines()
    b.send("PAUSE\n")
    assert b.run == "PAUSE" and "EVT,PAUSE" in b.read_lines()
    b.send("GO\n")
    assert b.run == "RUN"
    b.set_mode(3)                                # 손 3 정지 (사람 접근 등)
    assert b.run == "STOP" and "EVT,STOP,MODE" in b.read_lines()
    b.set_mode(1)
    b.send("GO\n")
    assert b.run == "STOP"                       # GO로는 잠김이 풀리지 않음
    b.press_reset()
    b.send("HOLD\n")
    assert b.run == "STOP" and b.latch == "HOLD"


# ---------- 도착 감지 ----------


def test_streak_counter_levels():
    c = StreakCounter(stable_frames=3, clear_frames=2)
    assert [c.update("INSIDE").arrived for _ in range(4)] == [False, False, True, True]
    assert not c.update("EDGE").arrived
    assert [c.update("EMPTY").cleared for _ in range(3)] == [False, True, True]


def test_box_inside():
    roi = (0, 0, 100, 100)
    assert box_inside((20, 20, 50, 50), roi, 10)
    assert not box_inside((5, 20, 50, 50), roi, 10)     # 왼쪽 가장자리에 걸침
    assert not box_inside((20, 20, 75, 50), roi, 10)    # 오른쪽 가장자리에 걸침


def test_crop_box_square_with_margin():
    from PIL import Image

    img = Image.new("RGB", (640, 480))
    assert crop_box(img, (100, 100, 100, 50), 0.2).size == (140, 140)
    assert crop_box(img, (0, 0, 100, 50), 0.2).size == (120, 95)   # 화면 밖은 잘림
    assert bottle_image(img, None, [0, 0, 200, 100], "box").size == (200, 100)   # 박스 없으면 판정 구역


def test_arrival_detector_with_opencv():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from vision.bottle.detect import ArrivalDetector

    d = ArrivalDetector(roi=[50, 50, 350, 250], stable_frames=2, clear_frames=2)
    empty = np.full((300, 400, 3), 90, np.uint8)
    assert d.update(empty).status == "NO_BASELINE"
    d.set_baseline(empty)
    assert d.update(empty).status == "EMPTY"
    frame = empty.copy()
    frame[120:180, 150:260] = 230                        # 구역 한가운데 밝은 병
    det = d.update(frame)
    assert det.status == "INSIDE" and not det.arrived
    det = d.update(frame)
    assert det.arrived
    x, y, w, h = det.box
    assert 50 < x < 150 and 50 < y < 120                 # 화면 좌표 (구역 원점 더함)
    edge = empty.copy()
    edge[120:180, 40:120] = 230                          # 구역 왼쪽 가장자리에 걸침
    assert d.update(edge).status == "EDGE"


# ---------- 실행기: 모의 화면으로 병이 들어와 멈추고, 찍고, 기록하고, 다시 출발 ----------


class Recorder:
    def __init__(self):
        self.msgs = []

    def publish(self, topic, payload, retain=False):
        self.msgs.append((topic, payload))


def test_runner_mock_end_to_end(tmp_path, monkeypatch):
    clock = {"t": 0}
    monkeypatch.setattr("app.line.now_ms", lambda: clock["t"])
    belt = SimBelt()
    belt.press_reset()
    vision = MockVision(belt)
    ctl = LineController(settle_ms=100, resume_delay_ms=200)
    rec = Recorder()
    r = LineRunner({"app": {}, "vision": {}}, vision, belt, ctl, rec, capture_dir=tmp_path)
    states = set()
    for _ in range(1500):                                 # 30초 흉내 (20ms 간격)
        clock["t"] += 20
        r.step()
        states.add(ctl.state)
        if sum(1 for t, _ in rec.msgs if t == "pet/judgment") >= 2:
            break
    judgments = [m for t, m in rec.msgs if t == "pet/judgment"]
    assert len(judgments) >= 2, states
    assert {"SETTLE", "RESUME_WAIT", "LEAVE"} <= states
    assert "PAUSE" in belt.sent and "GO" in belt.sent
    j = judgments[0]
    assert j["trigger"] == "CAM" and j["cls"] in ("clear_nolabel", "clear_label", "color_nolabel", "color_label")
    assert (tmp_path / j["img"]).is_file() and (tmp_path / j["full"]).is_file()
    assert j["img"].startswith(j["img"][:8] + "/W_")      # 날짜 폴더 / W_ 파일 이름
    assert r.preview()                                    # 대시보드 실시간 화면
