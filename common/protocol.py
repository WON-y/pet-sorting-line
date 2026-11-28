"""통신·모드·판정 규격의 파이썬 구현.

기준 문서: docs/spec/protocol.md, docs/spec/modes_and_states.md
이 파일을 바꾸면 위 문서와 tests/test_protocol.py도 함께 고친다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum

RADIO_MAX_LEN = 19
KST = timezone(timedelta(hours=9))


# ---------- 운전 모드·안전 단계 (modes_and_states.md 1~3절) ----------
class Mode(IntEnum):
    AUTO = 1
    SLOW = 2
    LOCKOUT = 4
    HELP = 5  # 선택 S1


class Danger(IntEnum):
    NONE = 0
    WARN = 1
    STOP = 2


def effective_state(mode: Mode, danger: Danger) -> str:
    """우선순위: 위험 정지 > 점검 잠금 > 접근 경고 > 저속 > 자동."""
    if danger == Danger.STOP:
        return "STOP"
    if mode == Mode.LOCKOUT:
        return "LOCKOUT"
    if danger == Danger.WARN:
        return "WARN"
    if mode == Mode.SLOW:
        return "SLOW"
    return "AUTO"


# ---------- 판정 (modes_and_states.md 4절, 4클래스·2단계 분기) ----------
CLASS_TO_CODE = {
    "clear_nolabel": "OK",
    "clear_label": "NG",
    "color_nolabel": "CO",
    "color_label": "CO",
}
RECHECK = "RE"
CODES = ("OK", "CO", "NG", "RE")
CODE_TO_HAND = {"OK": None, "CO": 1, "NG": 2, "RE": 2}
HAND_STATES = ("RDY", "OPEN", "DONE", "SAFE", "ERR")


# ---------- 라디오 메시지 (protocol.md 1절) ----------
def _check(msg: str) -> str:
    if len(msg) > RADIO_MAX_LEN:
        raise ValueError(f"라디오 메시지는 {RADIO_MAX_LEN}자 이내: {msg!r}")
    return msg


def encode_mode(mode: Mode | int) -> str:
    return _check(f"M{int(Mode(mode))}")


def encode_danger(level: Danger | int) -> str:
    return _check(f"D{int(Danger(level))}")


def encode_judgment(bottle_id: int, code: str) -> str:
    if code not in CODES:
        raise ValueError(f"판정 코드는 {CODES} 중 하나: {code!r}")
    return _check(f"J{bottle_id % 1000},{code}")


def encode_heartbeat(seq: int) -> str:
    return _check(f"HB3,{seq % 100}")


@dataclass(frozen=True)
class RadioMsg:
    kind: str            # MODE, DANGER, JUDGMENT, HEARTBEAT, HAND, ACK
    a: int | None = None  # 모드 번호, 단계, 병 id, seq, 손 번호
    b: str | None = None  # 판정 코드, 손 상태, ACK 병 id(문자열)


def parse_radio(msg: str) -> RadioMsg | None:
    """모르는 메시지는 None (규격: 무시)."""
    msg = msg.strip()
    try:
        if len(msg) == 2 and msg[0] == "M" and msg[1].isdigit():
            return RadioMsg("MODE", int(Mode(int(msg[1]))))
        if len(msg) == 2 and msg[0] == "D" and msg[1].isdigit():
            return RadioMsg("DANGER", int(Danger(int(msg[1]))))
        if msg.startswith("HB3,"):
            return RadioMsg("HEARTBEAT", int(msg[4:]))
        if msg.startswith("ACK"):
            hand, bid = msg[3:].split(",")
            return RadioMsg("ACK", int(hand), bid)
        if msg[0] == "J":
            bid, code = msg[1:].split(",")
            if code in CODES:
                return RadioMsg("JUDGMENT", int(bid), code)
        if msg[0] == "H" and msg[1].isdigit():
            hand, state = msg[1:].split(",")
            if state in HAND_STATES:
                return RadioMsg("HAND", int(hand), state)
    except (ValueError, IndexError):
        return None
    return None


# ---------- 게이트웨이 시리얼 (protocol.md 2절) ----------
def gateway_tx(radio_msg: str) -> str:
    return f"TX:{_check(radio_msg)}\n"


def parse_gateway_line(line: str) -> tuple[str, str] | None:
    """('RX', 라디오메시지) / ('PIN', 'STOP'|'RUN') / ('GW', 'BOOT')."""
    line = line.strip()
    if ":" not in line:
        return None
    head, body = line.split(":", 1)
    if head in ("RX", "PIN", "GW"):
        return head, body
    return None


# ---------- 게이트웨이 → 우노 모드 핀 (protocol.md 3절) ----------
# (P1,P0) 2비트. 카드·수신호 번호 → 핀 값. 선이 빠지면 11(점검 잠금)로 읽혀 멈춘다.
UNO_PIN_MODES = {1: 0b01, 2: 0b10, 3: 0b00, 4: 0b11}
UNO_RUN_MODES = (1, 2)          # 이 모드일 때만 리셋 버튼으로 재가동할 수 있다

# ---------- 우노 시리얼 (protocol.md 4절) ----------
# 재가동 명령은 없다. 재가동은 리셋 버튼으로만 (safety_rules.md 1절).
ARDUINO_COMMANDS = ("PAUSE", "GO", "HOLD", "PING")
STOP_CAUSES = ("POWERON", "HB", "MODE", "ESTOP", "HOLD", "IR")
BELT_STATES = ("RUN", "PAUSE", "STOP")


def arduino_cmd(cmd: str) -> str:
    if cmd not in ARDUINO_COMMANDS:
        raise ValueError(f"우노 명령은 {ARDUINO_COMMANDS} 중 하나: {cmd!r}")
    return cmd + "\n"


def parse_arduino_line(line: str) -> tuple[str, ...] | None:
    parts = tuple(line.strip().split(","))
    if not parts or parts[0] not in ("EVT", "STATE", "PONG"):
        return None
    return parts


# ---------- MQTT (protocol.md 5절) ----------
TOPICS = ("judgment", "sort", "mode", "safety", "hand", "state")


def topic(name: str, prefix: str = "pet", sub: str | int | None = None) -> str:
    if name not in TOPICS:
        raise ValueError(f"토픽은 {TOPICS} 중 하나: {name!r}")
    return f"{prefix}/{name}" + (f"/{sub}" if sub is not None else "")


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def event_type(topic_name: str, payload: dict) -> str:
    """MQTT 토픽 → DB events.type (data_and_logging.md 1절)."""
    leaf = topic_name.split("/")[1] if "/" in topic_name else topic_name
    if leaf == "safety":
        return str(payload.get("event", "STOP"))
    return {"judgment": "JUDGMENT", "sort": "SORT", "mode": "MODE", "hand": "HAND"}.get(leaf, "ERROR")
