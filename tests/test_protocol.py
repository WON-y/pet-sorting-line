"""규격(docs/spec/protocol.md)과 common/protocol.py가 맞는지 확인한다."""
import pytest

from common import protocol as p


def test_radio_messages_fit_19_chars():
    for msg in [p.encode_mode(1), p.encode_danger(2), p.encode_judgment(999, "RE"), p.encode_heartbeat(99)]:
        assert len(msg) <= p.RADIO_MAX_LEN


def test_encode_examples_match_spec():
    assert p.encode_mode(2) == "M2"
    assert p.encode_danger(2) == "D2"
    assert p.encode_judgment(12, "CO") == "J12,CO"
    assert p.encode_judgment(1000, "OK") == "J0,OK"   # 999 다음은 0
    assert p.encode_heartbeat(100) == "HB3,0"


def test_mode_3_is_not_used():
    with pytest.raises(ValueError):
        p.encode_mode(3)


@pytest.mark.parametrize("msg,kind,a,b", [
    ("M4", "MODE", 4, None), ("D1", "DANGER", 1, None), ("HB3,7", "HEARTBEAT", 7, None),
    ("J12,NG", "JUDGMENT", 12, "NG"), ("H2,DONE", "HAND", 2, "DONE"), ("ACK1,12", "ACK", 1, "12"),
])
def test_parse_radio(msg, kind, a, b):
    r = p.parse_radio(msg)
    assert r == p.RadioMsg(kind, a, b)


@pytest.mark.parametrize("msg", ["", "X1", "M3", "J12,XX", "H1,FLY", "hello"])
def test_unknown_messages_are_ignored(msg):
    assert p.parse_radio(msg) is None


def test_priority_order():
    assert p.effective_state(p.Mode.LOCKOUT, p.Danger.STOP) == "STOP"
    assert p.effective_state(p.Mode.LOCKOUT, p.Danger.WARN) == "LOCKOUT"
    assert p.effective_state(p.Mode.SLOW, p.Danger.WARN) == "WARN"
    assert p.effective_state(p.Mode.SLOW, p.Danger.NONE) == "SLOW"
    assert p.effective_state(p.Mode.AUTO, p.Danger.NONE) == "AUTO"


def test_class_codes_and_hands():
    assert p.CLASS_TO_CODE["clear_nolabel"] == "OK"
    assert p.CLASS_TO_CODE["clear_label"] == "NG"
    assert p.CLASS_TO_CODE["color_label"] == "CO"
    # 4클래스·2단계 분기 (modes_and_states.md 4절): 내용물 클래스 없음
    assert set(p.CLASS_TO_CODE) == {"clear_nolabel", "clear_label", "color_nolabel", "color_label"}
    assert p.CLASS_TO_CODE["color_nolabel"] == "CO"
    assert p.CODE_TO_HAND["CO"] == 1 and p.CODE_TO_HAND["NG"] == 2 and p.CODE_TO_HAND["RE"] == 2
    assert p.CODE_TO_HAND == {"OK": None, "CO": 1, "NG": 2, "RE": 2}


def test_gateway_and_arduino_lines():
    assert p.gateway_tx("J1,CO") == "TX:J1,CO\n"
    assert p.parse_gateway_line("RX:D2") == ("RX", "D2")
    assert p.parse_gateway_line("PIN:STOP") == ("PIN", "STOP")
    assert p.parse_gateway_line("garbage") is None
    assert p.arduino_cmd("GO") == "GO\n"
    assert p.arduino_cmd("PAUSE") == "PAUSE\n"
    for cmd in ("RESET", "RUN", "ARM", "SPD,N"):
        with pytest.raises(ValueError):
            p.arduino_cmd(cmd)   # 재가동은 리셋 버튼으로만, 속도는 모드 핀으로만
    assert p.parse_arduino_line("EVT,STOP,IR") == ("EVT", "STOP", "IR")


def test_topics():
    assert p.topic("judgment") == "pet/judgment"
    assert p.topic("hand", sub=1) == "pet/hand/1"
    with pytest.raises(ValueError):
        p.topic("unknown")


def test_uno_mode_pins_fail_safe():
    # 선이 빠지면 INPUT_PULLUP으로 11 → 점검 잠금(4) = 멈춤. 1·2만 리셋으로 출발 가능
    assert p.UNO_PIN_MODES == {1: 0b01, 2: 0b10, 3: 0b00, 4: 0b11}
    assert p.UNO_RUN_MODES == (1, 2)
    assert set(p.STOP_CAUSES) >= {"POWERON", "HB", "MODE", "HOLD"}
