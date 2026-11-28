"""app 상태 머신 (docs/spec/modes_and_states.md 3·5절)."""
from app.controller import LineController
from common import protocol as p


def kinds(acts, kind):
    return [a for a in acts if a[0] == kind]


def running(**kw) -> LineController:
    c = LineController(settle_ms=100, resume_delay_ms=500, **kw)
    c.on_arduino(("EVT", "RUN"), 0)
    return c


def judge(c, cls="clear_nolabel", code="OK", t=200):
    assert c.on_detect(0) == [("arduino", "PAUSE")]
    assert c.tick(50) == []                      # 멈춘 뒤 settle_ms 기다림
    assert c.tick(100) == [("capture", c.bottle_id)]
    return c.on_decision(cls, code, 0.95, 1, t, {"img": "a.jpg", "full": "b.jpg"})


def test_camera_detect_pauses_judges_and_auto_resumes():
    c = running()
    acts = judge(c)
    j = kinds(acts, "publish")[0]
    assert j[1] == "judgment" and j[2]["code"] == "OK" and j[2]["img"] == "a.jpg" and j[2]["trigger"] == "CAM"
    assert not kinds(acts, "gateway")            # 분기(sorting) 꺼짐: 손에 보내지 않음
    assert c.state == "RESUME_WAIT"
    assert c.tick(600) == []                     # resume_delay_ms 전
    assert c.tick(700) == [("arduino", "GO")]    # 자동 출발
    assert c.state == "LEAVE"
    assert c.on_detect(800) == []                # 같은 병이 아직 구역 안 → 다시 판정하지 않음
    c.on_clear(900)
    assert c.state == "IDLE"


def test_detect_ignored_unless_belt_running():
    c = LineController()
    assert c.on_detect(0) == []                  # 켜자마자는 STOP(잠김)
    c.on_arduino(("EVT", "RUN"), 0)
    c.on_arduino(("STATE", "PAUSE", "N"), 0)
    assert c.on_detect(0) == []


def test_manual_capture_works_when_stopped():
    c = LineController(settle_ms=0)
    assert c.on_manual(0) == []                  # 벨트가 멈춰 있으면 PAUSE 없이 바로 찍음
    assert c.tick(0) == [("capture", 0)]
    assert c.trigger == "MANUAL"


def test_ir_arrive_is_backup_trigger():
    c = running()
    c.on_arduino(("EVT", "ARRIVE"), 0)
    assert c.state == "SETTLE" and c.trigger == "IR" and c.belt == "PAUSE"


def test_sorting_ng_waits_for_ack_and_done():
    c = running(sorting=True)
    acts = judge(c, "clear_label", "NG")
    assert ("gateway", "J0,NG") in acts and c.state == "WAIT_ACK"
    c.on_radio(p.parse_radio("ACK2,0"), 300)
    assert c.state == "WAIT_SORT"
    acts = c.on_radio(p.parse_radio("H2,DONE"), 1500)
    assert any(a[0] == "publish" and a[1] == "sort" for a in acts)
    assert c.state == "RESUME_WAIT"


def test_sorting_no_ack_retries_once_then_holds():
    c = running(sorting=True, ack_timeout_ms=100)
    judge(c, "color_label", "CO", t=0)
    assert kinds(c.tick(150), "gateway")         # 한 번 다시 보냄
    acts = c.tick(300)
    assert ("arduino", "HOLD") in acts and c.state == "IDLE"


def test_stop_aborts_current_bottle():
    c = running()
    c.on_detect(0)
    acts = c.on_arduino(("EVT", "STOP", "MODE"), 50)
    assert c.state == "IDLE" and c.belt == "STOP" and c.stop_cause == "MODE"
    assert any(a[0] == "publish" and a[1] == "sort" and a[2]["result"] == "ABORTED" for a in acts)
    assert any(a[0] == "publish" and a[1] == "safety" and a[2]["cause"] == "MODE" for a in acts)


def test_lockout_ignores_mode_1():
    c = LineController()
    c.on_radio(p.parse_radio("M4"), 0)
    assert c.mode == p.Mode.LOCKOUT
    assert c.on_radio(p.parse_radio("M1"), 10) == []
    assert c.mode == p.Mode.LOCKOUT


def test_controller_never_commands_restart():
    """재가동은 리셋 버튼으로만: 상태 머신은 우노에 PAUSE·GO·HOLD 말고는 보내지 않는다."""
    c = running(sorting=True)
    acts = judge(c, "clear_label", "NG")
    for msg in ["M1", "M2", "M4", "D0", "D1", "D2", "ACK2,0", "H2,DONE"]:
        acts += c.on_radio(p.parse_radio(msg), 0)
    acts += c.tick(10_000) + c.on_arduino(("EVT", "STOP", "HB"), 0) + c.on_arduino(("EVT", "RUN"), 0)
    for a in kinds(acts, "arduino"):
        assert a[1] in ("PAUSE", "GO", "HOLD")
