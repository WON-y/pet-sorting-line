"""라인 상태 머신 (docs/spec/modes_and_states.md 3·5절).

하드웨어·시간·네트워크를 직접 만지지 않는 순수 로직이다. 입력을 받으면 '할 일(Action)' 목록을 돌려주고,
line.py가 그 일을 실제로 실행한다. 그래서 pytest로 하드웨어 없이 시험할 수 있다.

Action 형식:
  ("gateway", 라디오메시지)       게이트웨이로 TX
  ("arduino", 명령)               우노로 보냄 (PAUSE, GO, HOLD)
  ("publish", 토픽이름, payload)   기록 (토픽이름은 protocol.TOPICS 중 하나)
  ("capture", 병id)               사진 촬영 + 판정 시작

병 한 개의 흐름:
  IDLE ─(웹캠 도착 감지 → PAUSE / IR 도착 EVT,ARRIVE / 수동 촬영)→ SETTLE ─(settle_ms)→ CAPTURE
  CAPTURE ─(판정)→ [sorting이면 WAIT_ACK → WAIT_SORT] → RESUME_WAIT ─(resume_delay_ms, GO)→ LEAVE
  LEAVE ─(판정 구역이 빔)→ IDLE
이 프로그램은 재가동 명령을 보내지 않는다. 잠긴 벨트는 리셋 버튼으로만 다시 돈다.
"""
from __future__ import annotations

from common import protocol as p

Action = tuple

# 이 상태에서 정지·잠금이 걸리면 그 병은 끝까지 처리되지 못한 것 (ABORTED 기록)
_IN_PROGRESS = ("SETTLE", "CAPTURE", "WAIT_ACK", "WAIT_SORT")


class LineController:
    def __init__(self, ack_timeout_ms: int = 1500, settle_ms: int = 400, resume_delay_ms: int = 2000,
                 sorting: bool = False):
        self.mode = p.Mode.AUTO
        self.danger = p.Danger.NONE
        self.belt = "STOP"            # 우노 상태: RUN, PAUSE, STOP (켜면 잠김)
        self.speed = "N"
        self.stop_cause: str | None = None
        self.state = "IDLE"           # IDLE, SETTLE, CAPTURE, WAIT_ACK, WAIT_SORT, RESUME_WAIT, LEAVE
        self.bottle_id = -1
        self.trigger: str | None = None   # CAM(웹캠), IR(도착 센서), MANUAL(대시보드)
        self.code: str | None = None
        self.ack_timeout_ms, self.settle_ms = ack_timeout_ms, settle_ms
        self.resume_delay_ms, self.sorting = resume_delay_ms, sorting
        self._due_ms = 0
        self._sent_at_ms = 0
        self._retried = False

    @property
    def running(self) -> bool:
        return self.belt != "STOP"

    # ---------- 공통 ----------
    def state_payload(self) -> dict:
        return {"ts": p.now_iso(), "src": "app", "run": self.belt, "speed": self.speed,
                "mode": int(self.mode), "danger": int(self.danger),
                "state": p.effective_state(self.mode, self.danger), "line": self.state,
                "bottle": self.bottle_id, "cause": self.stop_cause}

    def _new_bottle(self, trigger: str, now_ms: int) -> None:
        self.bottle_id = (self.bottle_id + 1) % 1000
        self.trigger, self.code = trigger, None
        self.state, self._due_ms = "SETTLE", now_ms + self.settle_ms

    def _abort(self, reason: str) -> list[Action]:
        acts: list[Action] = []
        if self.state in _IN_PROGRESS and self.bottle_id >= 0:
            acts.append(("publish", "sort", {"ts": p.now_iso(), "src": "app", "id": self.bottle_id,
                                             "result": "ABORTED", "reason": reason}))
        self.state, self.code = "IDLE", None
        return acts

    def _resume(self, now_ms: int) -> list[Action]:
        """판정(·분기)이 끝났다 → 잠시 뒤 벨트 자동 출발."""
        self.state, self._due_ms = "RESUME_WAIT", now_ms + self.resume_delay_ms
        return []

    # ---------- 비전 (웹캠 도착 감지) ----------
    def on_detect(self, now_ms: int) -> list[Action]:
        """병이 판정 구역에 완전히 들어온 상태. 벨트가 돌고 있을 때만 멈추고 판정한다."""
        if self.state != "IDLE" or self.belt != "RUN":
            return []
        self._new_bottle("CAM", now_ms)
        return [("arduino", "PAUSE")]

    def on_clear(self, now_ms: int) -> list[Action]:
        """판정 구역이 비었다 → 다음 병을 받는다."""
        if self.state == "LEAVE":
            self.state = "IDLE"
        return []

    def on_manual(self, now_ms: int) -> list[Action]:
        """대시보드 '지금 촬영'. 벨트가 돌고 있으면 멈추고 찍는다."""
        if self.state != "IDLE":
            return []
        self._new_bottle("MANUAL", now_ms)
        return [("arduino", "PAUSE")] if self.belt == "RUN" else []

    def on_decision(self, cls: str, code: str, conf: float, frames: int, now_ms: int,
                    extra: dict | None = None) -> list[Action]:
        """extra: 사진 경로(img, full)·모델 세부(detail)처럼 기록에 덧붙일 값."""
        if self.state != "CAPTURE":
            return []
        self.code = code
        payload = {"ts": p.now_iso(), "src": "app", "id": self.bottle_id, "cls": cls, "code": code,
                   "conf": round(conf, 3), "frames": frames, "trigger": self.trigger}
        acts: list[Action] = [("publish", "judgment", payload | (extra or {}))]
        if not self.sorting:
            return acts + self._resume(now_ms)
        if p.CODE_TO_HAND[code] is None:   # 적합: 손이 움직이지 않음
            return acts + self._sorted(None, now_ms)
        self.state, self._sent_at_ms, self._retried = "WAIT_ACK", now_ms, False
        return acts + [("gateway", p.encode_judgment(self.bottle_id, code))]

    def _sorted(self, hand: int | None, now_ms: int) -> list[Action]:
        acts: list[Action] = [("publish", "sort", {"ts": p.now_iso(), "src": "app", "id": self.bottle_id,
                                                   "hand": hand, "result": "DONE"})]
        return acts + self._resume(now_ms)

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
            if new == p.Mode.LOCKOUT:
                acts += [("arduino", "HOLD")] + self._abort("lockout")
        elif msg.kind == "DANGER":
            level = p.Danger(msg.a)
            if level == self.danger:
                return []
            self.danger = level
            event = {0: "CLEAR", 1: "WARN", 2: "STOP"}[int(level)]
            acts.append(("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": int(level),
                                               "event": event, "cause": "RADIO"}))
            if level == p.Danger.STOP:
                acts += self._abort("danger")  # 실제 정지는 우노가 이미 했음 (모드 핀)
        elif msg.kind == "ACK" and self.state == "WAIT_ACK" and int(msg.b or -1) == self.bottle_id:
            self.state = "WAIT_SORT"
        elif msg.kind == "HAND":
            acts.append(("publish", "hand", {"ts": p.now_iso(), "src": "app", "hand": msg.a, "state": msg.b}))
            if msg.b == "DONE" and self.state == "WAIT_SORT":
                acts += self._sorted(msg.a, now_ms)
        return acts

    # ---------- 우노 ----------
    def on_arduino(self, parts: tuple[str, ...], now_ms: int) -> list[Action]:
        if parts[0] == "STATE" and len(parts) >= 3:
            if parts[1] in p.BELT_STATES:
                self.belt, self.speed = parts[1], parts[2]
            return []
        if parts[0] != "EVT" or len(parts) < 2:
            return []
        kind = parts[1]
        if kind == "PAUSE":
            self.belt = "PAUSE"
        elif kind == "ARRIVE":                      # IR 도착 센서가 스스로 멈춤 (웹캠 감지의 보조)
            self.belt = "PAUSE"
            if self.state == "IDLE":
                self._new_bottle("IR", now_ms)
        elif kind == "STOP":
            self.belt = "STOP"
            self.stop_cause = parts[2] if len(parts) > 2 else "UNKNOWN"
            return [("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": 2, "event": "STOP",
                                           "cause": self.stop_cause})] + self._abort("stop")
        elif kind == "RUN":
            self.belt, self.stop_cause = "RUN", None
            if self.danger == p.Danger.STOP:
                self.danger = p.Danger.NONE
            return [("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": 0, "event": "RUN",
                                           "cause": "RESET"})]
        return []

    # ---------- 시간 ----------
    def tick(self, now_ms: int) -> list[Action]:
        """대기 시간 처리. 실행 루프가 주기적으로 부른다."""
        if self.state == "SETTLE" and now_ms >= self._due_ms:
            self.state = "CAPTURE"
            return [("capture", self.bottle_id)]
        if self.state == "RESUME_WAIT" and now_ms >= self._due_ms:
            self.state = "LEAVE"
            return [("arduino", "GO")]
        if self.state == "WAIT_ACK" and now_ms - self._sent_at_ms > self.ack_timeout_ms:
            if not self._retried:
                self._retried, self._sent_at_ms = True, now_ms
                return [("gateway", p.encode_judgment(self.bottle_id, self.code or p.RECHECK))]
            return [("arduino", "HOLD"), ("publish", "safety", {"ts": p.now_iso(), "src": "app", "level": 0,
                                                                 "event": "ERROR", "cause": "NO_ACK"})] + \
                self._abort("no_ack")
        return []
