"""시험용 가상 벨트. 실제 우노(safety/belt_controller) 펌웨어의 시리얼 동작을 흉내 낸다.

센서·컨베이어 없이 대시보드에서 전체 흐름을 시험하기 위한 것이다. 실제 우노와 같은 규칙을 따른다.
- 켜면 잠김(STOP, POWERON). 모드가 1·2일 때 리셋 버튼(press_reset)을 눌러야만 RUN
- 모드 3(정지)·4(점검 잠금)가 되면 즉시 잠김
- PAUSE → 검사 멈춤, GO → 다시 RUN, HOLD → 잠김
- 1초마다 STATE 줄

링크(SerialLink·FakeLink)와 같은 send / read_lines를 가진다.
"""
from __future__ import annotations

from collections import deque

from common import protocol as p


class SimBelt:
    is_sim = True

    def __init__(self, mode: int = 1, state_period_ms: int = 1000):
        self.mode = mode                 # 손 3 카드·수신호 흉내 (1 자동, 2 저속, 3 정지, 4 점검 잠금)
        self.latch: str | None = "POWERON"
        self.paused = False
        self.position = 0.0              # 벨트가 움직인 거리 (모의 화면용, 임의 단위)
        self.state_period_ms = state_period_ms
        self._last_state = -10**9
        self._last_step: int | None = None
        self._out: deque[str] = deque([f"EVT,STOP,{self.latch}"])
        self.sent: list[str] = []

    # ---- 상태 ----
    @property
    def run(self) -> str:
        if self.latch:
            return "STOP"
        return "PAUSE" if self.paused else "RUN"

    @property
    def speed(self) -> str:
        return "S" if self.mode == 2 else "N"

    def moving(self) -> bool:
        return self.run == "RUN"

    def status(self) -> dict:
        return {"sim": True, "run": self.run, "speed": self.speed, "mode": self.mode, "latch": self.latch}

    def _stop(self, cause: str) -> None:
        if self.latch:
            return
        self.latch, self.paused = cause, False
        self._out.append(f"EVT,STOP,{cause}")

    # ---- 사람 조작 흉내 (대시보드 시험 버튼) ----
    def set_mode(self, mode: int) -> None:
        if mode not in p.UNO_PIN_MODES:
            raise ValueError("모드는 1~4")
        self.mode = mode
        if mode not in p.UNO_RUN_MODES:
            self._stop("MODE")

    def press_reset(self) -> str:
        """리셋 버튼. 성공하면 'OK', 아니면 거절 이유."""
        if not self.latch:
            return "NOT_LATCHED"
        if self.mode not in p.UNO_RUN_MODES:
            self._out.append("RESET,REFUSED,mode not 1 or 2")
            return "MODE_NOT_1_OR_2"
        self.latch, self.paused = None, False
        self._out.append("EVT,RUN")
        return "OK"

    def trip(self, cause: str = "HB") -> None:
        """위험 정지 흉내 (하트비트 끊김 등)."""
        self._stop(cause)

    # ---- 링크 인터페이스 ----
    def send(self, text: str) -> None:
        cmd = text.strip()
        self.sent.append(cmd)
        if cmd == "PAUSE" and self.run == "RUN":
            self.paused = True
            self._out.append("EVT,PAUSE")
        elif cmd == "GO" and not self.latch:
            self.paused = False
        elif cmd == "HOLD":
            self._stop("HOLD")
        elif cmd == "PING":
            self._out.append("PONG")

    def step(self, now_ms: int) -> None:
        if self._last_step is not None and self.moving():
            self.position += (now_ms - self._last_step) * (0.5 if self.mode == 2 else 1.0)
        self._last_step = now_ms
        if now_ms - self._last_state >= self.state_period_ms:
            self._last_state = now_ms
            self._out.append(f"STATE,{self.run},{self.speed}")

    def read_lines(self) -> list[str]:
        out = list(self._out)
        self._out.clear()
        return out
