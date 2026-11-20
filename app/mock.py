"""모의 하드웨어. 실제 게이트웨이·우노·웹캠 대신 가짜 메시지를 만들어 전체 흐름을 시험한다.

- 3초마다 병 도착(EVT,ARRIVE)
- 판정은 무작위 클래스 (가끔 낮은 신뢰도 → 재검사)
- 판정을 보내면 손이 ACK → DONE으로 응답
- 가끔 접근 경고(D1), 드물게 위험 정지(EVT,STOP,IR) 후 재가동
"""
from __future__ import annotations

import random

from common import protocol as p
from communication.serial_bridge.links import FakeLink

CLASSES = ["clear_nolabel", "clear_label", "color_nolabel", "color_label"]


class MockHardware:
    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
        self.gateway, self.arduino = FakeLink(), FakeLink()
        self.next_arrive = 1000
        self.stopped_until = 0
        self.warn_until = 0
        self.pending: list[tuple[int, str]] = []   # (시각, 게이트웨이에 넣을 줄)
        self.arduino.inject("EVT,RUN")             # 카드 1 + 리셋으로 이미 시작했다고 가정

    def predict(self, bottle_id: int) -> tuple[str, float]:
        """병 하나는 같은 클래스로 보이고, 약 7% 병은 신뢰도가 낮아 재검사가 된다."""
        r = random.Random(bottle_id * 7919)
        cls, unsure = r.choice(CLASSES), r.random() < 0.07
        return cls, (self.rng.uniform(0.3, 0.6) if unsure else self.rng.uniform(0.8, 0.99))

    def step(self, now: int, ctl) -> None:
        # 게이트웨이로 보낸 판정에 손이 응답
        for line in self.gateway.sent:
            if line.startswith("TX:J"):
                msg = p.parse_radio(line[3:])
                hand = p.CODE_TO_HAND[msg.b]
                self.pending += [(now + 200, f"RX:ACK{hand},{msg.a}"), (now + 1400, f"RX:H{hand},DONE")]
        self.gateway.sent.clear()
        self.arduino.sent.clear()
        for _t, line in [x for x in self.pending if x[0] <= now]:
            self.gateway.inject(line)
        self.pending = [x for x in self.pending if x[0] > now]

        # 위험 정지 후 재가동
        if self.stopped_until and now >= self.stopped_until:
            self.stopped_until = 0
            self.arduino.inject("EVT,RUN")
            return
        if self.stopped_until:
            return
        # 접근 경고
        if self.warn_until and now >= self.warn_until:
            self.warn_until = 0
            self.gateway.inject("RX:D0")
        if not self.warn_until and self.rng.random() < 0.0005:
            self.warn_until = now + 3000
            self.gateway.inject("RX:D1")
        # 드물게 위험 정지
        if self.rng.random() < 0.0001:
            self.stopped_until = now + 4000
            self.arduino.inject("EVT,STOP,IR")
            return
        # 병 도착
        if now >= self.next_arrive and ctl.state == "IDLE":
            self.next_arrive = now + 3000
            self.arduino.inject("EVT,ARRIVE")
