"""모의 실행. 웹캠·벨트·손 없이 전체 흐름을 대시보드에서 볼 수 있게 가짜 화면과 응답을 만든다.

- MockVision: 회색 벨트 위로 병 그림이 흘러가는 화면. 가상 벨트(SimBelt)가 돌 때만 움직인다.
  판정은 그림의 실제 클래스를 쓰고, 약 7%는 신뢰도가 낮아 재검사가 된다.
- MockHands: 판정을 게이트웨이로 보내면(sorting 켰을 때) 손이 ACK → DONE으로 응답
- MockOperator: 처음에 리셋 버튼을 눌러 주고, 드물게 하트비트 끊김 정지 → 4초 뒤 다시 리셋

모의 이벤트도 실제와 같은 규격(common/protocol.py)으로 만든다. 모의에서만 쓰는 메시지를 만들지 않는다.
"""
from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw

from common import protocol as p
from communication.serial_bridge.links import FakeLink
from vision.bottle.classifier import combine
from vision.bottle.detect import Detection, StreakCounter, box_inside
from vision.bottle.preprocess import bottle_image

CLASSES = ["clear_nolabel", "clear_label", "color_nolabel", "color_label"]
W, H = 640, 360
DEFAULT_ROI = [200, 40, 440, 320]
PX_PER_MS = 0.16                      # 보통 속도에서 화면 이동 속도 (160 px/초)
BOTTLE_W, BOTTLE_H = 150, 56


class MockVision:
    def __init__(self, belt, vcfg: dict | None = None, seed: int = 0):
        vcfg = vcfg or {}
        d = vcfg.get("detect", {})
        self.belt, self.vcfg = belt, vcfg
        self.rng = random.Random(seed)
        self.roi = list(DEFAULT_ROI)
        self.edge_margin = d.get("edge_margin", 10)
        self.counter = StreakCounter(d.get("stable_frames", 5), d.get("clear_frames", 10))
        self.baseline = True           # 모의 화면은 처음부터 빈 벨트 기준이 있다고 본다
        self._pos = belt.position
        self.serial = 0
        self._spawn()
        self.det = Detection("EMPTY")
        self.frame = self._render()

    def _spawn(self) -> None:
        self.serial += 1
        self.cls = self.rng.choice(CLASSES)
        self.x = -BOTTLE_W - self.rng.randint(20, 220)

    def box(self) -> tuple[int, int, int, int]:
        return int(self.x), 150, BOTTLE_W, BOTTLE_H

    # ---- 화면 ----
    def _render(self) -> Image.Image:
        img = Image.new("RGB", (W, H), (70, 72, 78))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 110, W, 250), fill=(95, 98, 105))                     # 벨트
        off = int(self.belt.position * PX_PER_MS) % 40
        for x in range(-40 + off, W, 40):
            d.line((x, 110, x, 250), fill=(85, 88, 95), width=2)               # 벨트 무늬 (움직임 표시)
        x, y, w, h = self.box()
        clear = self.cls.startswith("clear")
        body = (200, 222, 236) if clear else ((40, 120, 60) if self.serial % 2 else (120, 70, 30))
        d.rounded_rectangle((x, y, x + w - 18, y + h), radius=18, fill=body, outline=(240, 244, 248), width=2)
        d.rectangle((x + w - 20, y + 18, x + w, y + h - 18), fill=(30, 90, 200))  # 뚜껑
        if self.cls.endswith("_label") and not self.cls.endswith("nolabel"):
            d.rectangle((x + 40, y + 2, x + 95, y + h - 2), fill=(210, 40, 40))   # 라벨
        return img

    def grab(self, belt_moving: bool = True) -> Detection:
        moved = (self.belt.position - self._pos) * PX_PER_MS
        self._pos = self.belt.position
        self.x += moved
        if self.x > W:
            self._spawn()
        self.frame = self._render()
        bx, by, bw, bh = self.box()
        rx1, ry1, rx2, ry2 = self.roi
        overlaps = bx < rx2 and bx + bw > rx1 and by < ry2 and by + bh > ry1
        if not overlaps:
            status = "EMPTY"
        else:
            status = "INSIDE" if box_inside(self.box(), (rx1, ry1, rx2 - rx1, ry2 - ry1), self.edge_margin) else "EDGE"
        self.det = self.counter.update(status, self.box() if overlaps else None)
        return self.det

    # ---- 설정 ----
    def set_baseline(self) -> None:
        self.baseline = True
        self.counter.reset()

    def set_roi(self, roi) -> None:
        self.roi = [int(v) for v in roi] if roi else list(DEFAULT_ROI)
        self.counter.reset()

    def info(self) -> dict:
        return {"source": "mock", "mock": True, "width": W, "height": H, "roi": self.roi,
                "baseline": self.baseline, "detect": self.det.status, "box": self.det.box,
                "model": "모의 (색 + 라벨)"}

    # ---- 촬영·판정 ----
    def capture(self):
        box = self.det.box
        bottle = bottle_image(self.frame, box, self.roi, self.vcfg.get("crop_mode", "box"),
                              self.vcfg.get("crop_margin", 0.2))
        return self.frame.copy(), bottle, box

    def classify(self, bottle: Image.Image) -> tuple[str, float, dict]:
        """색 모델·라벨 모델을 흉내 낸다. 약 7%는 한쪽 모델이 확신하지 못함."""
        r = random.Random(self.serial * 7919)
        color, label = self.cls.split("_")
        cc, lc = r.uniform(0.85, 0.99), r.uniform(0.8, 0.99)
        if r.random() < 0.07:
            cc = r.uniform(0.3, 0.6)
        cls, conf = combine(color, cc, label, lc)
        return cls, conf, {"color": color, "color_conf": round(cc, 3), "label": label, "label_conf": round(lc, 3)}

    def preview_jpeg(self, text: str = "") -> bytes:
        img = self.frame.copy()
        d = ImageDraw.Draw(img)
        d.rectangle(self.roi, outline=(255, 255, 0), width=3)
        if self.det.box:
            x, y, w, h = self.det.box
            d.rectangle((x, y, x + w, y + h), outline=(0, 255, 0) if self.det.status == "INSIDE" else (0, 200, 255),
                        width=2)
        if text:
            d.text((10, 10), text, fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        return buf.getvalue()

    def close(self) -> None:
        pass


class MockHands:
    """게이트웨이 흉내. TX:J… 를 받으면 손이 ACK → DONE 응답 (sorting 켰을 때만 쓰임)."""

    def __init__(self):
        self.link = FakeLink()
        self.pending: list[tuple[int, str]] = []

    def step(self, now: int) -> None:
        for line in self.link.sent:
            if line.startswith("TX:J"):
                msg = p.parse_radio(line[3:])
                hand = p.CODE_TO_HAND[msg.b]
                self.pending += [(now + 200, f"RX:ACK{hand},{msg.a}"), (now + 1400, f"RX:H{hand},DONE")]
        self.link.sent.clear()
        for _t, line in [x for x in self.pending if x[0] <= now]:
            self.link.inject(line)
        self.pending = [x for x in self.pending if x[0] > now]


class MockOperator:
    """사람 흉내: 시작할 때 리셋 버튼, 드물게 하트비트 끊김 정지 → 4초 뒤 다시 리셋."""

    def __init__(self, belt, seed: int = 0, trip_prob: float = 0.0001):
        self.belt, self.rng, self.trip_prob = belt, random.Random(seed), trip_prob
        self.reset_at: int | None = 0

    def step(self, now: int) -> None:
        if self.reset_at is not None and now >= self.reset_at:
            self.belt.set_mode(1)
            self.belt.press_reset()
            self.reset_at = None
        elif self.reset_at is None and self.belt.run != "STOP" and self.rng.random() < self.trip_prob:
            self.belt.trip("HB")
            self.reset_at = now + 4000
