"""라인 실행기. 웹캠·우노·게이트웨이·기록을 상태 머신(LineController)에 연결해 루프를 돈다.

대시보드(웹)는 다른 스레드에서 돌기 때문에, 대시보드 버튼은 call()로 명령을 넣고 이 루프가 처리한다.
정지 경로에 끼지 않는다 (docs/spec/safety_rules.md). 이 프로그램이 죽어도 벨트는 우노가 멈춘다.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future
from pathlib import Path

from app.controller import LineController
from common import protocol as p
from vision.bottle.decide import decide

log = logging.getLogger("app.line")


def now_ms() -> int:
    return int(time.monotonic() * 1000)


class LocalRecorder:
    """노트북 하나로 실행할 때: 대시보드 handle_message로 바로 SQLite에 기록 (MQTT·도커 없음)."""

    def __init__(self, handle_message):
        self.handle_message = handle_message

    def publish(self, topic: str, payload: dict, retain: bool = False) -> None:
        self.handle_message(topic, payload)


class LineRunner:
    def __init__(self, cfg: dict, vision, belt, ctl: LineController, publisher, gateway=None,
                 capture_dir: str | Path = "data/captures", helpers: list | None = None):
        self.cfg, self.vision, self.belt, self.ctl = cfg, vision, belt, ctl
        self.publisher, self.gateway = publisher, gateway
        self.capture_dir = Path(capture_dir)
        self.helpers = helpers or []          # 모의 실행 도우미 (step(now) 를 가진 객체)
        self.prefix = cfg.get("mqtt", {}).get("topic_prefix", "pet")
        acfg, vcfg = cfg.get("app", {}), cfg.get("vision", {})
        self.state_publish_ms = acfg.get("state_publish_ms", 1000)
        self.preview_ms = cfg.get("dashboard", {}).get("preview_ms", 200)
        self.frames, self.conf_threshold = vcfg.get("frames", 1), vcfg.get("conf_threshold", 0.6)
        self.is_sim = getattr(belt, "is_sim", False)
        self.last_judgment: dict | None = None
        self.last_error: str | None = None
        self._cmds: queue.Queue = queue.Queue()
        self._preview: bytes | None = None
        self._preview_lock = threading.Lock()
        self._last_state = self._last_preview = -10**9
        self._stop = threading.Event()

    # ---------- 대시보드에서 부르는 것 (다른 스레드) ----------
    def call(self, fn, timeout: float = 5.0):
        """fn을 실행 루프 스레드에서 실행하고 결과를 돌려준다."""
        fut: Future = Future()
        self._cmds.put((fn, fut))
        return fut.result(timeout)

    def preview(self) -> bytes | None:
        with self._preview_lock:
            return self._preview

    def status(self) -> dict:
        c = self.ctl
        belt = self.belt.status() if self.is_sim else {"sim": False, "run": c.belt, "speed": c.speed,
                                                       "latch": c.stop_cause}
        return {"belt": belt, "line": c.state, "bottle": c.bottle_id, "trigger": c.trigger,
                "sorting": c.sorting, "vision": self.vision.info(), "last": self.last_judgment,
                "error": self.last_error}

    def stop(self) -> None:
        self._stop.set()

    # ---------- 실행 ----------
    def execute(self, actions: list) -> None:
        for act in actions:
            kind = act[0]
            if kind == "arduino":
                self.belt.send(p.arduino_cmd(act[1]))
            elif kind == "gateway":
                if self.gateway is not None:
                    self.gateway.send(p.gateway_tx(act[1]))
            elif kind == "publish":
                retain = act[1] == "state"
                self.publisher.publish(p.topic(act[1], self.prefix), act[2], retain=retain)
            elif kind == "capture":
                self._capture(act[1])

    def _capture(self, bottle_id: int) -> None:
        preds: list[tuple[str, float]] = []
        full = bottle = None
        detail: dict = {}
        try:
            for i in range(self.frames):
                if i:
                    self.vision.grab(False)
                full, bottle, _box = self.vision.capture()
                cls, conf, detail = self.vision.classify(bottle)
                preds.append((cls, conf))
            self.last_error = None
        except Exception as e:   # 모델·카메라 문제가 있어도 라인은 재검사로 넘어간다
            log.exception("판정 실패")
            self.last_error = f"판정 실패: {e}"
        cls, code = decide(preds, self.frames, self.conf_threshold)
        conf = min((c for _, c in preds), default=0.0)
        extra = self._save(bottle_id, full, bottle) if full is not None else {}
        if detail:
            extra["detail"] = detail          # 색·라벨 모델 각각의 결과 (마지막 프레임)
        self.last_judgment = {"id": bottle_id, "cls": cls, "code": code, "conf": round(conf, 3),
                              "ts": p.now_iso(), "trigger": self.ctl.trigger} | extra
        self.execute(self.ctl.on_decision(cls, code, conf, len(preds), now_ms(), extra))

    def _save(self, bottle_id: int, full, bottle) -> dict:
        """재학습용 사진 저장 (data_and_logging.md 3절 파일 이름 규칙: 출처 W = 벨트 웹캠)."""
        try:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            day = self.capture_dir / stamp[:8]
            day.mkdir(parents=True, exist_ok=True)
            base = f"W_{stamp}_{bottle_id:03d}"
            full.convert("RGB").save(day / f"{base}_full.jpg", quality=95)
            bottle.convert("RGB").save(day / f"{base}_crop.jpg", quality=95)
            return {"img": f"{stamp[:8]}/{base}_crop.jpg", "full": f"{stamp[:8]}/{base}_full.jpg"}
        except Exception as e:
            log.warning("사진 저장 실패: %s", e)
            self.last_error = f"사진 저장 실패: {e}"
            return {}

    def step(self) -> None:
        t = now_ms()
        while not self._cmds.empty():
            fn, fut = self._cmds.get_nowait()
            try:
                fut.set_result(fn())
            except Exception as e:
                fut.set_exception(e)
        if self.is_sim:
            self.belt.step(t)
        for h in self.helpers:
            h.step(t)
        if self.gateway is not None:
            for line in self.gateway.read_lines():
                parsed = p.parse_gateway_line(line)
                if parsed and parsed[0] == "RX":
                    msg = p.parse_radio(parsed[1])
                    if msg:
                        self.execute(self.ctl.on_radio(msg, t))
        for line in self.belt.read_lines():
            parts = p.parse_arduino_line(line)
            if parts:
                self.execute(self.ctl.on_arduino(parts, t))
        det = self.vision.grab(self.ctl.belt == "RUN")
        if det.arrived:
            self.execute(self.ctl.on_detect(t))
        if det.cleared:
            self.execute(self.ctl.on_clear(t))
        self.execute(self.ctl.tick(t))
        if t - self._last_state >= self.state_publish_ms:
            self._last_state = t
            self.execute([("publish", "state", self.ctl.state_payload())])
        if t - self._last_preview >= self.preview_ms:
            self._last_preview = t
            text = f"belt {self.ctl.belt} | {self.ctl.state} | {det.status}"
            jpeg = self.vision.preview_jpeg(text)
            with self._preview_lock:
                self._preview = jpeg

    def run(self, duration_s: float | None = None, period_s: float = 0.02) -> None:
        start = time.monotonic()
        while not self._stop.is_set() and (duration_s is None or time.monotonic() - start < duration_s):
            self.step()
            time.sleep(period_s)
