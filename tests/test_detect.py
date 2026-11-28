"""웹캠 도착 감지의 빈 벨트 기준 (docs/spec/modes_and_states.md 5절, vision/bottle/detect.py).

벨트가 돌면 반사·이음매가 판정 구역을 지나간다. 1장 기준은 이것을 병으로 잘못 보고,
여러 장 기준(자리별 허용치)은 걸러야 한다. 진짜 물체는 여전히 잡아야 한다.
"""
import re
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from vision.bottle.detect import ArrivalDetector  # noqa: E402

ROI = [20, 20, 380, 280]
BELT_EMPTY = Path(__file__).resolve().parents[1] / "data" / "belt_empty"


def belt_frame(shift: int) -> "np.ndarray":
    """초록 벨트 + 벨트를 따라 움직이는 밝은 반사 띠 (벨트 한 바퀴 = 400px)."""
    f = np.full((300, 400, 3), (60, 110, 40), np.uint8)
    x = shift % 400
    f[:, x:x + 60] = (130, 190, 120)                 # 반사 띠 (밝기 차이 약 70)
    if x + 60 > 400:
        f[:, : x + 60 - 400] = (130, 190, 120)
    return f


def learn(d: ArrivalDetector, frames, collect_s=10.0, n=40, verify=()):
    d.start_learning(collect_s=collect_s, frames=n, verify_s=1.0, now=0.0)
    step = collect_s / len(frames)
    for i, f in enumerate(frames):
        assert d.update(f, now=i * step).status == "LEARNING"
    d.update(frames[-1], now=collect_s)              # 모으기 끝 → 기준 만들고 확인 시작
    for i, f in enumerate(verify):
        assert d.update(f, now=collect_s + 0.01 * (i + 1)).status == "LEARNING"
    d.update(frames[-1], now=collect_s + 2)          # 확인 끝


def test_single_baseline_mistakes_moving_glare_for_bottle():
    d = ArrivalDetector(ROI, stable_frames=1)
    d.set_baseline(belt_frame(0))
    statuses = {d.analyze(belt_frame(s))[0] for s in range(0, 400, 20)}
    assert statuses - {"EMPTY"}                       # 반사 띠가 움직이면 '물체'로 봄


def test_learned_baseline_ignores_glare_but_finds_bottle():
    d = ArrivalDetector(ROI, stable_frames=1)
    learn(d, [belt_frame(s) for s in range(0, 400, 5)], verify=[belt_frame(s) for s in range(3, 400, 37)])
    assert d.check["kind"] == "multi" and d.check["ok"] and d.check["false"] == 0 and d.check["frames"] > 0
    assert all(d.analyze(belt_frame(s))[0] == "EMPTY" for s in range(2, 400, 13))
    bottle = belt_frame(123)
    bottle[110:190, 120:280] = (200, 200, 200)        # 구역 한가운데 병
    det = d.update(bottle)
    assert det.status == "INSIDE" and det.arrived


def test_no_arrival_while_learning_and_check_reports_false_alarms():
    d = ArrivalDetector(ROI, stable_frames=1)
    bottle = belt_frame(0)
    bottle[110:190, 120:280] = (200, 200, 200)
    d.start_learning(collect_s=1.0, frames=10, verify_s=1.0, now=0.0)
    for k in range(10):                               # 10장 모으는 중 1장에 병 (사람이 실수로 올림)
        frame = bottle if k == 5 else belt_frame(0)
        assert not d.update(frame, now=k / 10).arrived   # 모으는 중에는 도착 신호 없음
    assert d.learning_info(now=0.95)["phase"] == "collect"
    d.update(belt_frame(0), now=1.0)                  # 기준 생성
    assert d.learning_info(now=1.0)["phase"] == "verify"
    d.update(bottle, now=1.5)                         # 확인 중에 물체 → 오감지로 셈
    d.update(belt_frame(0), now=2.1)
    assert d.learn is None and d.check["false"] >= 1 and d.check["ok"] is False
    assert d.check["excluded"] == 1                   # 병이 찍힌 1장은 허용치 계산에서 뺌


def test_object_during_collection_does_not_blind_that_spot():
    """모으는 중 병이 지나가도 그 자리의 허용치가 커지지 않아, 나중에 거기 온 병을 잡는다."""
    d = ArrivalDetector(ROI, stable_frames=1)
    bottle = belt_frame(0)
    bottle[110:190, 120:280] = (200, 200, 200)
    frames = [belt_frame(s) for s in range(0, 400, 10)]
    frames[10] = frames[11] = bottle                  # 40장 중 2장
    learn(d, frames)
    assert d.check["excluded"] == 2
    faint = belt_frame(200).astype(int)
    faint[110:190, 120:280] += 45                     # 옅은 물체 (투명 병 흉내)
    assert d.analyze(faint.clip(0, 255).astype("uint8"))[0] == "INSIDE"


def test_single_baseline_when_belt_stopped_and_roi_change_resets():
    d = ArrivalDetector(ROI)
    d.set_baseline(belt_frame(0))
    assert d.check == {"kind": "single"} and d.tol is None
    d.start_learning(now=0.0)
    d.set_roi([0, 0, 200, 200])                       # 구역이 바뀌면 기준·진행 중인 학습 모두 버림
    assert d.baseline is None and d.learn is None and d.check is None
    assert d.update(belt_frame(0)).status == "NO_BASELINE"


@pytest.mark.skipif(not BELT_EMPTY.is_dir(), reason="data/belt_empty 없음 (팀 공유 드라이브에서 받기)")
def test_real_empty_belt_photos_no_false_alarm():
    """빈 벨트 사진(224×224): 짝수 번호로 기준을 만들고 홀수 번호에서 오감지 0."""
    files = sorted(BELT_EMPTY.glob("*.jpg"), key=lambda f: int(re.findall(r"(\d+)\.jpg$", f.name)[0]))
    # cv2.imread는 윈도우에서 한글 경로(바탕 화면)를 못 열어 바이트로 읽어 디코딩한다
    imgs = [cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR) for f in files]
    assert len(imgs) > 100
    belt = [10, 85, 214, 180]                         # 흰 가장자리를 뺀 벨트 안쪽
    d = ArrivalDetector(belt, edge_margin=3)
    learn(d, imgs[0::2], collect_s=float(len(imgs[0::2])), n=60)
    false = [i for i in range(1, len(imgs), 2) if d.analyze(imgs[i])[0] != "EMPTY"]
    assert false == []
