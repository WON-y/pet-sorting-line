"""MQTT 발행 (docs/spec/protocol.md 5절). 브로커가 없어도 app이 멈추지 않게 실패는 경고만 한다."""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(self, host: str = "localhost", port: int = 1883):
        self.client = None
        try:
            import paho.mqtt.client as mqtt

            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pet-app")
            self.client.connect(host, port, keepalive=30)
            self.client.loop_start()
        except Exception as e:  # 대시보드는 기록용이라 없어도 라인은 돌아야 함
            log.warning("MQTT 연결 실패(기록 없이 계속): %s", e)
            self.client = None

    def publish(self, topic: str, payload: dict, retain: bool = False) -> None:
        if self.client is None:
            log.info("[MQTT 미연결] %s %s", topic, payload)
            return
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=retain)
