"""app 상태 머신 (docs/spec/modes_and_states.md 3·5절)."""
from app.controller import LineController
from common import protocol as p


def kinds(acts, kind):
    return [a for a in acts if a[0] == kind]


def test_ok_bottle_goes_straight_through():
    c = LineController()
    assert c.on_arduino(("EVT", "ARRIVE"), 0) == [("capture", 0)]
    acts = c.on_decision("clear_nolabel", "OK", 0.95, 1, 10)
    assert ("arduino", "GO") in acts
    assert not kinds(acts, "gateway")          # 적합은 손이 안 움직임
    assert c.state == "IDLE"


def test_ng_bottle_waits_for_ack_and_done():
    c = LineController()
    c.on_arduino(("EVT", "ARRIVE"), 0)
    acts = c.on_decision("clear_label", "NG", 0.9, 3, 10)
    assert ("gateway", "J0,NG") in acts and c.state == "WAIT_ACK"
    c.on_radio(p.parse_radio("ACK2,0"), 100)
    assert c.state == "WAIT_SORT"
    acts = c.on_radio(p.parse_radio("H2,DONE"), 1500)
    assert ("arduino", "GO") in acts and c.state == "IDLE"


def test_no_ack_retries_once_then_holds():
    c = LineController(ack_timeout_ms=100)
    c.on_arduino(("EVT", "ARRIVE"), 0)
    c.on_decision("color_label", "CO", 0.9, 3, 0)
    assert kinds(c.tick(150), "gateway")        # 한 번 다시 보냄
    acts = c.tick(300)
    assert ("arduino", "HOLD") in acts and c.state == "IDLE"


def test_lockout_ignores_mode_1():
    c = LineController()
    c.on_radio(p.parse_radio("M4"), 0)
    assert c.mode == p.Mode.LOCKOUT
    assert c.on_radio(p.parse_radio("M1"), 10) == []
    assert c.mode == p.Mode.LOCKOUT


def test_mode_1_arms_reset():
    c = LineController()
    c.on_radio(p.parse_radio("M2"), 0)
    acts = c.on_radio(p.parse_radio("M1"), 10)
    assert ("arduino", "ARM") in acts


def test_stop_aborts_current_bottle():
    c = LineController()
    c.on_arduino(("EVT", "ARRIVE"), 0)
    c.on_decision("clear_label", "NG", 0.9, 3, 0)
    acts = c.on_arduino(("EVT", "STOP", "IR"), 50)
    assert c.state == "IDLE"
    assert any(a[0] == "publish" and a[1] == "sort" and a[2]["result"] == "ABORTED" for a in acts)


def test_controller_never_commands_restart():
    """재가동은 버튼으로만: 상태 머신은 우노에 재가동 명령을 보내지 않는다."""
    c = LineController()
    for msg in ["M1", "M2", "M4", "D0", "D1", "D2"]:
        for a in c.on_radio(p.parse_radio(msg), 0):
            assert not (a[0] == "arduino" and a[1] in ("RUN", "START", "RESET"))
