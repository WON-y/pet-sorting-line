"""웹캠 병 도착 감지 (docs/spec/modes_and_states.md 5절).

빈 벨트 기준 사진과 지금 화면을 비교해, 판정 구역 안에 물체가 '완전히' 들어왔는지 본다.
- 완전히 들어온 상태가 `stable_frames` 이상 이어지는 동안 arrived (그 프레임으로 판정)
- 구역이 `clear_frames` 이상 비어 있는 동안 cleared (다음 병을 받을 준비)
두 값은 '지금 그런 상태인가'를 매 프레임 알려 준다. 한 병을 한 번만 판정하는 일은 app 상태 머신이 맡는다.

빈 벨트 기준은 두 가지:
- 여러 장 (벨트가 돌 때, 기본): `baseline_s` 동안 `baseline_frames`장을 모아 자리마다 중앙값(평균 모습)과
  허용치(그 자리가 원래 흔들린 정도 + `tol_extra`, 최소 `tol_min`)를 만든다. 벨트 반사·이음매가 지나가도
  병으로 보지 않는다. 그 뒤 `verify_s` 동안 빈 벨트를 보며 오감지를 세어 결과(check)를 남긴다.
- 1장 (벨트가 멈춰 있을 때): 그 화면 1장과 비교, 모든 자리에 `diff_thresh` 하나.

정지 경로가 아니다 (안전 정지는 우노·센서·전선).
OpenCV·numpy는 ArrivalDetector를 쓸 때만 import 한다 (모의 실행·CI를 가볍게).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

Box = tuple[int, int, int, int]   # x, y, w, h (화면 좌표)


@dataclass
class Detection:
    status: str            # NO_BASELINE, LEARNING(기준 만드는 중), EMPTY, EDGE(가장자리에 걸침), INSIDE
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


# 자리별 허용치: 모은 사진(물체가 찍힌 사진은 뺀 뒤)에서 그 자리가 흔들린 최대값.
# 2026-11-28 빈 벨트 사진 370장 시험 (짝수로 만들고 홀수 185장으로 확인, tol_extra 10):
#   95% → 반사 구간(전체의 약 10%)을 버려 오감지 9~10장 / 99% → 오감지 1장 / 100% → 오감지 0장,
#   밝기 +30짜리 옅은 물체 37/37 감지. (1장 기준 diff_thresh 40: 오감지 15장, +30 물체 5/37)
TOL_PERCENTILE = 100
# 모으는 동안 확실한 물체(손·병)가 찍힌 사진은 허용치 계산에서 뺀다: 중앙값과 diff_thresh × 이 값 넘게 다른
# 덩어리가 있는 사진. 그냥 두면 그 자리의 허용치가 커져 나중에 거기 온 병을 놓친다.
OUTLIER_FACTOR = 2


class ArrivalDetector:
    """OpenCV 프레임(BGR)을 받아 Detection을 돌려준다. roi는 [x1, y1, x2, y2] 또는 None(화면 전체)."""

    def __init__(self, roi=None, diff_thresh: int = 40, min_area_frac: float = 0.03, edge_margin: int = 10,
                 stable_frames: int = 5, clear_frames: int = 10, tol_extra: int = 10, tol_min: int = 25):
        import cv2  # noqa: F401  (없으면 여기서 바로 알 수 있게)

        self.roi = list(roi) if roi else None
        self.diff_thresh, self.min_area_frac, self.edge_margin = diff_thresh, min_area_frac, edge_margin
        self.tol_extra, self.tol_min = tol_extra, tol_min
        self.counter = StreakCounter(stable_frames, clear_frames)
        self.baseline = None
        self.tol = None               # 자리별 허용치 (여러 장 기준일 때). None이면 diff_thresh 하나
        self.learn: dict | None = None   # 여러 장 기준을 만드는 중
        self.check: dict | None = None   # 마지막으로 만든 기준의 확인 결과

    @classmethod
    def from_config(cls, vcfg: dict) -> ArrivalDetector:
        d = vcfg.get("detect", {})
        return cls(vcfg.get("roi"), d.get("diff_thresh", 40), d.get("min_area_frac", 0.03), d.get("edge_margin", 10),
                   d.get("stable_frames", 5), d.get("clear_frames", 10), d.get("tol_extra", 10), d.get("tol_min", 25))

    # ---- 설정 ----
    def set_roi(self, roi) -> None:
        self.roi = list(roi) if roi else None
        self.baseline = self.tol = self.learn = self.check = None   # 구역이 바뀌면 기준을 다시 만들어야 한다
        self.counter.reset()

    def set_baseline(self, frame_bgr) -> None:
        """1장 기준 (벨트가 멈춰 있을 때)."""
        self.baseline, self.tol, self.learn = self._gray(self._region(frame_bgr)), None, None
        self.check = {"kind": "single"}
        self.counter.reset()

    def start_learning(self, collect_s: float = 20, frames: int = 60, verify_s: float = 10,
                       now: float | None = None) -> None:
        """여러 장 기준 만들기 시작 (빈 벨트가 돌고 있을 때). 이후 update()에 들어오는 프레임으로 진행한다."""
        now = time.monotonic() if now is None else now
        self.learn = {"phase": "collect", "start": now, "until": now + collect_s, "every": collect_s / max(1, frames),
                      "next": now, "frames": [], "verify_s": verify_s, "checked": 0, "false": 0}
        self.counter.reset()

    def learning_info(self, now: float | None = None) -> dict | None:
        if not self.learn:
            return None
        now = time.monotonic() if now is None else now
        return {"phase": self.learn["phase"], "left_s": round(max(0.0, self.learn["until"] - now), 1),
                "frames": len(self.learn["frames"])}

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

    @staticmethod
    def _level(g) -> float:
        """전체 밝기 (자동 노출 보정용). 평균이 아니라 중앙값: 큰 물체(손·병)가 있어도 벨트 밝기를 가리킨다."""
        import numpy as np

        return float(np.median(g[::4, ::4]))

    def roi_origin(self) -> tuple[int, int]:
        return (self.roi[0], self.roi[1]) if self.roi else (0, 0)

    def _blob(self, mask):
        """0/255 마스크 → 물체로 볼 만큼 큰 덩어리들 (조각을 합친 뒤 min_area_frac 이상)."""
        import cv2
        import numpy as np

        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.dilate(mask, np.ones((21, 21), np.uint8))   # 투명 병 조각 합치기
        h, w = mask.shape
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [c for c in contours if cv2.contourArea(c) >= self.min_area_frac * w * h]

    def _build(self, grays: list) -> int:
        """모은 사진 → 자리별 중앙값(기준)과 허용치. 물체가 찍혀 뺀 사진 수를 돌려준다."""
        import numpy as np

        stack = np.stack(grays).astype(np.float32)
        med = np.median(stack, axis=0)
        ref = self._level(med)
        offsets = np.array([ref - self._level(g) for g in stack], np.float32)
        stack += offsets[:, None, None]                    # 사진마다 전체 밝기 보정 (analyze와 같게)
        dev = np.abs(stack - med)
        limit = self.diff_thresh * OUTLIER_FACTOR
        keep = [i for i in range(len(dev)) if not self._blob((dev[i] > limit).astype(np.uint8) * 255)]
        if not keep:
            keep = list(range(len(dev)))
        self.baseline = np.clip(med, 0, 255).astype(np.uint8)
        tol = np.percentile(dev[keep], TOL_PERCENTILE, axis=0)
        self.tol = np.maximum(tol + self.tol_extra, self.tol_min).astype(np.float32)
        return len(dev) - len(keep)

    def _learn_step(self, frame_bgr, now: float) -> Detection:
        L = self.learn
        if L["phase"] == "collect":
            if now >= L["next"]:
                L["frames"].append(self._gray(self._region(frame_bgr)))
                L["next"] += L["every"]
            if now >= L["until"] and L["frames"]:
                L["collected"] = len(L["frames"])
                L["excluded"] = self._build(L["frames"])
                L.update(phase="verify", until=now + L["verify_s"], frames=[])
        else:
            status, _ = self.analyze(frame_bgr)
            L["checked"] += 1
            L["false"] += status != "EMPTY"
            if now >= L["until"]:
                # 모은 사진의 1/4 넘게 물체가 찍혔으면 빈 벨트가 아니었던 것 → 다시 만들기 권장
                ok = L["false"] == 0 and L["excluded"] * 4 <= L["collected"]
                self.check = {"kind": "multi", "frames": L["checked"], "false": L["false"], "ok": ok,
                              "collected": L["collected"], "excluded": L["excluded"],
                              "tol_mean": round(float(self.tol.mean()), 1), "tol_max": round(float(self.tol.max()), 1)}
                self.learn = None
                self.counter.reset()
        return Detection("LEARNING")

    # ---- 감지 ----
    def analyze(self, frame_bgr) -> tuple[str, Box | None]:
        """(상태, 화면 좌표 박스). 기준 사진이 없거나 크기가 다르면 NO_BASELINE."""
        import cv2
        import numpy as np

        region = self._region(frame_bgr)
        if self.baseline is None or region.shape[:2] != self.baseline.shape[:2]:
            return "NO_BASELINE", None
        g = self._gray(region).astype(np.int16)
        g += int(round(self._level(self.baseline) - self._level(g)))   # 자동 노출로 전체 밝기가 변하는 것 보정
        diff = np.abs(g - self.baseline.astype(np.int16))
        thresh = self.tol if self.tol is not None else self.diff_thresh
        big = self._blob((diff > thresh).astype(np.uint8) * 255)
        h, w = diff.shape
        if not big:
            return "EMPTY", None
        x, y, bw, bh = cv2.boundingRect(np.vstack(big))         # 조각을 모두 감싸는 박스 = 병 전체
        ox, oy = self.roi_origin()
        box = (ox + x, oy + y, bw, bh)
        inside = box_inside((x, y, bw, bh), (0, 0, w, h), self.edge_margin)
        return ("INSIDE" if inside else "EDGE"), box

    def update(self, frame_bgr, now: float | None = None) -> Detection:
        if self.learn:
            return self._learn_step(frame_bgr, time.monotonic() if now is None else now)
        status, box = self.analyze(frame_bgr)
        if status == "NO_BASELINE":
            self.counter.reset()
            return Detection(status)
        return self.counter.update(status, box)
