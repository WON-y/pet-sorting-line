"""통신·모드·판정 규격의 파이썬 구현.

기준 문서: docs/spec/protocol.md, docs/spec/modes_and_states.md
이 파일을 바꾸면 위 문서와 tests/test_protocol.py도 함께 고친다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum

KST = timezone(timedelta(hours=9))


# ---------- 운전 모드·안전 단계 (modes_and_states.md 1~3절) ----------
class Mode(IntEnum):
    """손 3이 라디오 `mode`로 보내는 번호 = 수신호·카드 번호. 도움 요청은 모드가 아니다(`help`)."""
    AUTO = 1
    SLOW = 2
    PAUSE = 3     # 일시 정지 (모드 핀 00, 우노 잠김)
    LOCKOUT = 4


class Danger(IntEnum):
    NONE = 0
    WARN = 1
    STOP = 2


def effective_state(mode: Mode, danger: Danger) -> str:
    """우선순위: 위험 정지 > 점검 잠금 > 일시 정지 > 접근 경고 > 저속 > 자동."""
    if danger == Danger.STOP:
        return "STOP"
    if mode == Mode.LOCKOUT:
        return "LOCKOUT"
    if mode == Mode.PAUSE:
        return "PAUSE"
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

# 판정 번호 (protocol.md 1절). 게이트웨이 시리얼 J0~J4, 라디오 jdg 값의 끝자리, 손 1·2 분기 규칙에 쓰인다.
# 2(내용물 남음)는 손 2 코드에는 있지만 지금 모델에 없는 클래스라 노트북은 보내지 않는다.
CODE_TO_JDG = {"RE": 0, "OK": 1, "NG": 3, "CO": 4}
JDG_TO_CODE = {v: k for k, v in CODE_TO_JDG.items()}


# ---------- 라디오 (protocol.md 1절) ----------
# micro:bit radio.sendValue(이름, 숫자). 노트북은 라디오를 직접 쓰지 않고 게이트웨이 시리얼로만 본다.
RADIO_NAMES = ("mode", "help", "dng", "jdg")


def jdg_value(seq: int, code: str) -> int:
    """라디오 jdg 값 = 순번 × 10 + 판정 번호 (게이트웨이가 만든다. 모의·시험용)."""
    return (seq % 1000) * 10 + CODE_TO_JDG[code]


# ---------- 게이트웨이 시리얼 (protocol.md 2절) ----------
def encode_judgment(code: str) -> str:
    """노트북 → 게이트웨이 판정 한 줄 (줄바꿈은 보내는 쪽이 붙임). 예: NG → 'J3'."""
    if code not in CODE_TO_JDG:
        raise ValueError(f"판정 코드는 {CODES} 중 하나: {code!r}")
    return f"J{CODE_TO_JDG[code]}"


@dataclass(frozen=True)
class GatewayMsg:
    kind: str             # ACK, MODE, HELP, DANGER, LINK, ERR
    a: int | None = None  # ACK 순번, 모드 번호, 0/1, 위험 단계, LINK 1(OK)/0(LOST)
    b: int | None = None  # ACK 판정 번호


def parse_gateway_line(line: str) -> GatewayMsg | None:
    """게이트웨이 → 노트북 한 줄. 모르는 줄·범위 밖 값은 None (규격: 무시)."""
    parts = line.strip().split(",")
    head = parts[0]
    try:
        if head == "ACK" and len(parts) == 3:
            seq, jdg = int(parts[1]), int(parts[2])
            return GatewayMsg("ACK", seq, jdg) if 0 <= jdg <= 4 else None
        if head == "MODE" and len(parts) == 2:
            return GatewayMsg("MODE", int(Mode(int(parts[1]))))
        if head == "HELP" and len(parts) == 2 and parts[1] in ("0", "1"):
            return GatewayMsg("HELP", int(parts[1]))
        if head == "DNG" and len(parts) == 2:
            return GatewayMsg("DANGER", int(Danger(int(parts[1]))))
        if head == "LINK" and len(parts) == 2 and parts[1] in ("OK", "LOST"):
            return GatewayMsg("LINK", 1 if parts[1] == "OK" else 0)
        if head == "ERR":
            return GatewayMsg("ERR")
    except ValueError:
        return None
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
