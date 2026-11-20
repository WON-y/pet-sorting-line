"""노트북 통합 실행. `python -m app` (실제 하드웨어) / `python -m app --mock` (하드웨어 없이).

역할: 게이트웨이·우노 시리얼을 읽고 → LineController에 넘기고 → 돌려받은 할 일을 실행한다.
정지 경로에는 끼지 않는다 (docs/spec/safety_rules.md). 이 프로그램이 죽어도 벨트는 우노가 멈춘다.
"""
from __future__ import annotations

import argparse
import logging
import os
import time

from app.controller import LineController
from app.mock import MockHardware
from common import protocol as p
from common.config import load_settings
from communication.serial_bridge.mqtt_pub import MqttPublisher
from vision.bottle.decide import decide

log = logging.getLogger("app")


def now_ms() -> int:
    return int(time.monotonic() * 1000)


def run(mock: bool, duration_s: float | None = None) -> None:
    cfg = load_settings()
    vcfg, acfg, mcfg = cfg["vision"], cfg["app"], cfg["mqtt"]
    prefix = mcfg.get("topic_prefix", "pet")
    mqtt = MqttPublisher(os.environ.get("MQTT_HOST", mcfg["host"]), int(os.environ.get("MQTT_PORT", mcfg["port"])))
    ctl = LineController(ack_timeout_ms=acfg["ack_timeout_ms"])

    if mock:
        hw = MockHardware()
        gateway, arduino, camera_predict = hw.gateway, hw.arduino, hw.predict
    else:
        from communication.serial_bridge.links import SerialLink
        from vision.bottle.camera import Camera
        from vision.bottle.classifier import BottleClassifier

        gateway = SerialLink(cfg["serial"]["gateway_port"], cfg["serial"]["baud"])
        arduino = SerialLink(cfg["serial"]["arduino_port"], cfg["serial"]["baud"])
        clf = BottleClassifier(vcfg["weights"], vcfg["roi"], vcfg["imgsz"], vcfg["letterbox_color"])
        cam = Camera(vcfg["camera_index"])

        def camera_predict(_bottle_id: int) -> tuple[str, float]:
            return clf.predict(cam.read_rgb())

    def execute(actions: list) -> None:
        for act in actions:
            kind = act[0]
            if kind == "gateway":
                gateway.send(p.gateway_tx(act[1]))
            elif kind == "arduino":
                arduino.send(p.arduino_cmd(act[1]))
            elif kind == "publish":
                mqtt.publish(p.topic(act[1], prefix), act[2])
            elif kind == "capture":
                preds = [camera_predict(act[1]) for _ in range(vcfg["frames"])]
                cls, code = decide(preds, vcfg["frames"], vcfg["conf_threshold"])
                conf = min(c for _, c in preds)
                execute(ctl.on_decision(cls, code, conf, len(preds), now_ms()))

    start, last_state = time.monotonic(), 0
    log.info("시작 (mock=%s)", mock)
    while duration_s is None or time.monotonic() - start < duration_s:
        t = now_ms()
        if mock:
            hw.step(t, ctl)
        for line in gateway.read_lines():
            parsed = p.parse_gateway_line(line)
            if parsed and parsed[0] == "RX":
                msg = p.parse_radio(parsed[1])
                if msg:
                    execute(ctl.on_radio(msg, t))
        for line in arduino.read_lines():
            parts = p.parse_arduino_line(line)
            if parts:
                execute(ctl.on_arduino(parts, t))
        execute(ctl.tick(t))
        if t - last_state >= acfg["state_publish_ms"]:
            mqtt.publish(p.topic("state", prefix), ctl.state_payload(), retain=True)
            last_state = t
        time.sleep(0.02)


def cli() -> None:
    ap = argparse.ArgumentParser(description="페트병 선별 라인 노트북 통합 실행")
    ap.add_argument("--mock", action="store_true", help="하드웨어 없이 가짜 이벤트로 실행")
    ap.add_argument("--duration", type=float, default=None, help="초 단위 실행 시간 (시험용)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run(args.mock, args.duration)


if __name__ == "__main__":
    cli()
