"""라인 상태 머신 (docs/spec/modes_and_states.md 3·5절).

하드웨어·시간·네트워크를 직접 만지지 않는 순수 로직이다. 입력을 받으면 '할 일(Action)' 목록을 돌려주고,
main.py가 그 일을 실제로 실행한다. 그래서 pytest로 하드웨어 없이 시험할 수 있다.

Action 형식:
  ("gateway", 라디오메시지)       게이트웨이로 TX
  ("arduino", 명령)               우노로 보냄 (GO, SPD,N ...)
  ("publish", 토픽이름, payload)   MQTT 발행 (토픽이름은 protocol.TOPICS 중 하나)
  ("capture", 병id)               웹캠 판정 시작
"""
from __future__ import annotations

from common import protocol as p

Action = tuple


class LineController:
    def __init__(self, ack_timeout_ms: int = 1500):
        self.mode = p.Mode.AUTO
        self.danger = p.Danger.NONE
        self.running = False          # 우노가 RUN 상태인가
        self.state = "IDLE"           # IDLE, CAPTURE, WAIT_ACK, WAIT_SORT
        self.bottle_id = -1
        self.code: str | None = None
        self.ack_timeout_ms = ack_timeout_ms
        self._sent_at_ms = 0
        self._retried = False

    # ---------- 공통 ----------
    def _state_payload(self) -> dict:
        return {"ts": p.now_iso(), "src": "app", "run": "RUN" if self.running else "STOP",
                "mode": int(self.mode), "danger": int(self.danger),
                "state": p.effective_state(self.mode, self.danger)}

    def _abort(self, reason: str) -> list[Action]:
        acts: list[Action] = []
        if self.state != "IDLE" and self.bottle_id >= 0:
            acts.append(("publish", "sort", {"ts": p.now_iso(), "src": "app", "id": self.bottle_id,
                                             "result": "ABORTED", "reason": reason}))
        self.state, self.code = "IDLE", None
        return acts

    # ---------- 라디오 (게이트웨이 RX) ----------
    def on_radio(self, msg: p.RadioMsg, now_ms: int, by: str = "card") -> list[Action]:
        acts: list[Action] = []
        if msg.kind == "MODE":
            new = p.Mode(msg.a)
            if self.mode == p.Mode.LOCKOUT and new == p.Mode.AUTO:
                return []  # 점검 잠금 중에는 1 무시 (4를 치운 뒤 처리는 손 3이 담당)
            if new == self.mode:
                return []
            self.mode = new
            acts.append(("publish", "mode", {"ts": p.now_iso(), "src": "app", "mode": int(new), "by": by}))
            if new == p.Mode.SLOW:
                acts.append(("arduino", "SPD,S"))
            elif new == p.Mode.LOCKOUT:
                acts += [("arduino", "HOLD")] + self._abort("lockout")
            elif new == p.Mode.AUTO:
                acts += [("arduino", "SPD,N"), ("arduino", "ARM")]  # 리셋 버튼을 받을 준비
        elif msg.kind == "DANGER":
            level = p.Danger(msg.a)
            if level == self.danger:
                return []
            self.danger = level
            event = {0: "CLEAR", 1: "WARN", 2: "STOP"}[int(level)]
            acts.append(("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": int(level),
                                               "event": event, "cause": "RADIO"}))
            if level == p.Danger.WARN:
                acts.append(("arduino", "SPD,S"))
            elif level == p.Danger.NONE and self.mode == p.Mode.AUTO:
                acts.append(("arduino", "SPD,N"))
            elif level == p.Danger.STOP:
                acts += self._abort("danger")  # 실제 정지는 우노가 이미 했음 (P0)
        elif msg.kind == "ACK" and self.state == "WAIT_ACK" and int(msg.b or -1) == self.bottle_id:
            self.state = "WAIT_SORT"
        elif msg.kind == "HAND":
            acts.append(("publish", "hand", {"ts": p.now_iso(), "src": "app", "hand": msg.a, "state": msg.b}))
            if msg.b == "DONE" and self.state == "WAIT_SORT":
                acts += self._finish()
        return acts

    # ---------- 우노 ----------
    def on_arduino(self, parts: tuple[str, ...], now_ms: int) -> list[Action]:
        if parts[0] != "EVT":
            return []
        kind = parts[1]
        if kind == "ARRIVE" and self.state == "IDLE":
            self.bottle_id = (self.bottle_id + 1) % 1000
            self.state = "CAPTURE"
            return [("capture", self.bottle_id)]
        if kind == "STOP":
            self.running = False
            cause = parts[2] if len(parts) > 2 else "UNKNOWN"
            return [("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": 2, "event": "STOP",
                                           "cause": cause})] + self._abort("stop")
        if kind == "RUN":
            self.running = True
            if self.danger == p.Danger.STOP:
                self.danger = p.Danger.NONE
            return [("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": 0, "event": "RUN",
                                           "cause": "RESET"}), ("gateway", p.encode_danger(0))]
        return []

    # ---------- 비전 ----------
    def on_decision(self, cls: str, code: str, conf: float, frames: int, now_ms: int) -> list[Action]:
        if self.state != "CAPTURE":
            return []
        self.code = code
        acts: list[Action] = [("publish", "judgment", {"ts": p.now_iso(), "src": "app", "id": self.bottle_id,
                                                       "cls": cls, "code": code, "conf": round(conf, 3),
                                                       "frames": frames})]
        if p.CODE_TO_HAND[code] is None:   # 적합: 손이 움직이지 않음
            return acts + self._finish()
        self.state, self._sent_at_ms, self._retried = "WAIT_ACK", now_ms, False
        return acts + [("gateway", p.encode_judgment(self.bottle_id, code))]

    def tick(self, now_ms: int) -> list[Action]:
        """ACK 시간 초과 처리. main 루프가 주기적으로 부른다."""
        if self.state == "WAIT_ACK" and now_ms - self._sent_at_ms > self.ack_timeout_ms:
            if not self._retried:
                self._retried, self._sent_at_ms = True, now_ms
                return [("gateway", p.encode_judgment(self.bottle_id, self.code or p.RECHECK))]
            return [("arduino", "HOLD"), ("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": 0,
                                                                 "event": "ERROR", "cause": "NO_ACK"})] + \
                self._abort("no_ack")
        return []

    def _finish(self) -> list[Action]:
        hand = p.CODE_TO_HAND.get(self.code or "OK")
        acts: list[Action] = [("arduino", "GO"),
                              ("publish", "sort", {"ts": p.now_iso(), "src": "app", "id": self.bottle_id,
                                                   "hand": hand, "result": "DONE"})]
        self.state, self.code = "IDLE", None
        return acts

    def state_payload(self) -> dict:
        return self._state_payload()
