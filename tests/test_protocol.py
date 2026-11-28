"""규격(docs/spec/protocol.md)과 common/protocol.py가 맞는지 확인한다."""
import pytest

from common import protocol as p


def test_judgment_numbers_match_microbit_code():
    # code/microbit: 0 재검사, 1 투명 적합, 2 내용물 남음(안 씀), 3 라벨 있음, 4 유색·불투명
    assert p.CODE_TO_JDG == {"RE": 0, "OK": 1, "NG": 3, "CO": 4}
    assert p.encode_judgment("NG") == "J3"
    assert p.encode_judgment("OK") == "J1"          # OK도 보낸다 (날개판을 나란히)
    with pytest.raises(ValueError):
        p.encode_judgment("XX")
    assert p.jdg_value(57, "CO") == 574             # 순번 × 10 + 판정 번호


def test_hands_divert_rule_matches_codes():
    # hand12_sorter.ts shouldDivert: 손 1은 4, 손 2는 0·2·3
    for code, jdg in p.CODE_TO_JDG.items():
        hand = 1 if jdg == 4 else (2 if jdg in (0, 2, 3) else None)
        assert p.CODE_TO_HAND[code] == hand


def test_mode_3_is_pause():
    assert p.Mode(3) == p.Mode.PAUSE
    assert p.UNO_PIN_MODES[int(p.Mode.PAUSE)] == 0b00
    with pytest.raises(ValueError):
        p.Mode(5)                                   # 도움 요청은 모드가 아니라 help


@pytest.mark.parametrize("line,kind,a,b", [
    ("ACK,57,4", "ACK", 57, 4), ("MODE,3", "MODE", 3, None), ("HELP,1", "HELP", 1, None),
    ("DNG,2", "DANGER", 2, None), ("LINK,OK", "LINK", 1, None), ("LINK,LOST", "LINK", 0, None),
    ("ERR,J9", "ERR", None, None), ("DNG,1\r", "DANGER", 1, None),
])
def test_parse_gateway_line(line, kind, a, b):
    assert p.parse_gateway_line(line) == p.GatewayMsg(kind, a, b)


@pytest.mark.parametrize("line", ["", "garbage", "MODE,5", "MODE,x", "DNG,3", "HELP,2", "LINK,MAYBE",
                                  "ACK,1,9", "ACK,1", "RX:M1", "PIN:STOP"])
def test_unknown_gateway_lines_are_ignored(line):
    assert p.parse_gateway_line(line) is None


def test_priority_order():
    assert p.effective_state(p.Mode.LOCKOUT, p.Danger.STOP) == "STOP"
    assert p.effective_state(p.Mode.LOCKOUT, p.Danger.WARN) == "LOCKOUT"
    assert p.effective_state(p.Mode.PAUSE, p.Danger.WARN) == "PAUSE"
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


def test_arduino_lines():
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
