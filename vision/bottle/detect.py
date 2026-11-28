"""웹캠 병 도착 감지 (docs/spec/modes_and_states.md 5절).

빈 벨트 기준 사진과 지금 화면을 비교해, 판정 구역 안에 물체가 '완전히' 들어왔는지 본다.
- 완전히 들어온 상태가 `stable_frames` 이상 이어지는 동안 arrived (그 프레임으로 판정)
- 구역이 `clear_frames` 이상 비어 있는 동안 cleared (다음 병을 받을 준비)
두 값은 '지금 그런 상태인가'를 매 프레임 알려 준다. 한 병을 한 번만 판정하는 일은 app 상태 머신이 맡는다.

정지 경로가 아니다 (안전 정지는 우노·센서·전선).
OpenCV·numpy는 ArrivalDetector를 쓸 때만 import 한다 (모의 실행·CI를 가볍게).
"""
from __future__ import annotations

from dataclasses import dataclass

Box = tuple[int, int, int, int]   # x, y, w, h (화면 좌표)


@dataclass
class Detection:
    status: str            # NO_BASELINE, EMPTY, EDGE(가장자리에 걸침), INSIDE
    box: Box | None = None
    arrived: bool = False  # 완전히 들어온 상태가 충분히 이어짐
    cleared: bool = False  # 빈 상태가 충분히 이어짐


class StreakCounter:
    """INSIDE·EMPTY 연속 프레임 수를 세서 도착·비었음을 알려 준다 (하드웨어 없이 시험 가능)."""

    def __init__(self, stable_frames: int = 5, clear_frames: int = 10):
        self.stable_frames, self.clear_frames = stable_frames, clear_frames
        self.inside = self.empty = 0

    def reset(self) -> None:
        self.inside = self.empty = 0

    def update(self, status: str, box: Box | None = None) -> Detection:
        self.inside = self.inside + 1 if status == "INSIDE" else 0
        self.empty = self.empty + 1 if status == "EMPTY" else 0
        return Detection(status, box, arrived=self.inside >= self.stable_frames,
                         cleared=self.empty >= self.clear_frames)


def box_inside(box: Box, roi: Box, edge_margin: int) -> bool:
    """box가 roi(x, y, w, h) 가장자리에서 edge_margin 이상 떨어져 완전히 안에 있는가."""
    x, y, w, h = box
    rx, ry, rw, rh = roi
    return (x - rx > edge_margin and y - ry > edge_margin
            and rx + rw - (x + w) > edge_margin and ry + rh - (y + h) > edge_margin)


class ArrivalDetector:
    """OpenCV 프레임(BGR)을 받아 Detection을 돌려준다. roi는 [x1, y1, x2, y2] 또는 None(화면 전체)."""

    def __init__(self, roi=None, diff_thresh: int = 40, min_area_frac: float = 0.03, edge_margin: int = 10,
                 stable_frames: int = 5, clear_frames: int = 10):
        import cv2  # noqa: F401  (없으면 여기서 바로 알 수 있게)

        self.roi = list(roi) if roi else None
        self.diff_thresh, self.min_area_frac, self.edge_margin = diff_thresh, min_area_frac, edge_margin
        self.counter = StreakCounter(stable_frames, clear_frames)
        self.baseline = None

    # ---- 설정 ----
    def set_roi(self, roi) -> None:
        self.roi = list(roi) if roi else None
        self.baseline = None          # 구역이 바뀌면 기준 사진을 다시 찍어야 한다
        self.counter.reset()

    def set_baseline(self, frame_bgr) -> None:
        self.baseline = self._gray(self._region(frame_bgr))
        self.counter.reset()

    # ---- 내부 ----
    def _region(self, frame_bgr):
        if not self.roi:
            return frame_bgr
        x1, y1, x2, y2 = self.roi
        return frame_bgr[y1:y2, x1:x2]

    @staticmethod
    def _gray(img_bgr):
        import cv2

        return cv2.GaussianBlur(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY), (9, 9), 0)

    def roi_origin(self) -> tuple[int, int]:
        return (self.roi[0], self.roi[1]) if self.roi else (0, 0)

    # ---- 감지 ----
    def analyze(self, frame_bgr) -> tuple[str, Box | None]:
        """(상태, 화면 좌표 박스). 기준 사진이 없거나 크기가 다르면 NO_BASELINE."""
        import cv2
        import numpy as np

        region = self._region(frame_bgr)
        if self.baseline is None or region.shape[:2] != self.baseline.shape[:2]:
            return "NO_BASELINE", None
        g = self._gray(region).astype(np.int16)
        g += int(self.baseline.mean() - g.mean())              # 자동 노출로 전체 밝기가 변하는 것 보정
        diff = np.abs(g - self.baseline.astype(np.int16))
        mask = (diff > self.diff_thresh).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.dilate(mask, np.ones((21, 21), np.uint8))   # 투명 병 조각 합치기
        h, w = mask.shape
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        big = [c for c in contours if cv2.contourArea(c) >= self.min_area_frac * w * h]
        if not big:
            return "EMPTY", None
        x, y, bw, bh = cv2.boundingRect(np.vstack(big))         # 조각을 모두 감싸는 박스 = 병 전체
        ox, oy = self.roi_origin()
        box = (ox + x, oy + y, bw, bh)
        inside = box_inside((x, y, bw, bh), (0, 0, w, h), self.edge_margin)
        return ("INSIDE" if inside else "EDGE"), box

    def update(self, frame_bgr) -> Detection:
        status, box = self.analyze(frame_bgr)
        if status == "NO_BASELINE":
            self.counter.reset()
            return Detection(status)
        return self.counter.update(status, box)
