"""웹캠(또는 녹화 영상) → 도착 감지 → 촬영 → 판정을 묶은 실제 비전 경로 (app/line.py가 사용).

모의 실행용 같은 모양의 클래스는 app/mock.py의 MockVision이다. 두 클래스는 같은 메서드를 가진다:
  grab(belt_moving)     새 프레임을 읽고 Detection을 돌려준다
  capture()             (전체 사진, 병 사진, 박스) — PIL 이미지, 레터박스 전
  classify(bottle)      (4클래스, 신뢰도, 세부) — 세부: 색·라벨 모델 각각의 결과
  preview_jpeg(text)    대시보드 실시간 화면용 JPEG (판정 구역·박스 표시)
  set_baseline() / set_roi(roi) / info()
OpenCV·ultralytics는 이 파일을 쓸 때만 필요하다 (requirements-hw.txt).
"""
from __future__ import annotations

import logging
import time

from PIL import Image

from .classifier import load_classifier, model_status
from .detect import ArrivalDetector, Detection
from .preprocess import bottle_image

log = logging.getLogger(__name__)
PREVIEW_WIDTH = 960      # 대시보드로 보내는 미리보기 폭 (전송량을 줄이려고 줄임)


class CameraVision:
    def __init__(self, vcfg: dict, video_file: str | None = None):
        import cv2

        self.cv2 = cv2
        self.vcfg = vcfg
        self.source = video_file or vcfg.get("video_file") or int(vcfg.get("camera_index", 0))
        self.is_file = isinstance(self.source, str)
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            raise RuntimeError(f"영상을 열 수 없습니다: {self.source}")
        if not self.is_file:
            w, h = vcfg.get("camera_size", [1920, 1080])
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.frame_period = 1.0 / (self.cap.get(cv2.CAP_PROP_FPS) or 30) if self.is_file else 0.0
        self._next_frame_at = 0.0
        d = vcfg.get("detect", {})
        self.detector = ArrivalDetector(vcfg.get("roi"), d.get("diff_thresh", 40), d.get("min_area_frac", 0.03),
                                        d.get("edge_margin", 10), d.get("stable_frames", 5),
                                        d.get("clear_frames", 10))
        self.frame = None
        self.det = Detection("NO_BASELINE")
        self._clf = None
        self._read()
        log.info("영상 입력: %s, %sx%s", self.source, *self.size())

    # ---- 입력 ----
    def _read(self) -> None:
        ok, frame = self.cap.read()
        if not ok and self.is_file:                     # 영상 끝 → 처음부터 다시
            self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("영상 프레임을 읽지 못했습니다")
        self.frame = frame

    def size(self) -> tuple[int, int]:
        h, w = self.frame.shape[:2]
        return w, h

    def grab(self, belt_moving: bool = True) -> Detection:
        """녹화 영상은 벨트가 멈추면 영상도 멈춘다 (실제 벨트처럼 보이게)."""
        if not self.is_file:
            self._read()
        elif belt_moving and time.monotonic() >= self._next_frame_at:
            self._next_frame_at = time.monotonic() + self.frame_period
            self._read()
        self.det = self.detector.update(self.frame)
        return self.det

    # ---- 설정 ----
    def set_baseline(self) -> None:
        self.detector.set_baseline(self.frame)

    def set_roi(self, roi) -> None:
        if roi:
            w, h = self.size()
            x1, y1, x2, y2 = (int(v) for v in roi)
            x1, x2 = sorted((max(0, min(w, x1)), max(0, min(w, x2))))
            y1, y2 = sorted((max(0, min(h, y1)), max(0, min(h, y2))))
            if x2 - x1 < 20 or y2 - y1 < 20:
                raise ValueError("판정 구역이 너무 작습니다")
            roi = [x1, y1, x2, y2]
        self.detector.set_roi(roi)

    def info(self) -> dict:
        w, h = self.size()
        return {"source": str(self.source), "mock": False, "width": w, "height": h,
                "roi": self.detector.roi, "baseline": self.detector.baseline is not None,
                "detect": self.det.status, "box": self.det.box, "model": model_status(self.vcfg)}

    # ---- 촬영·판정 ----
    def capture(self) -> tuple[Image.Image, Image.Image, tuple | None]:
        full = Image.fromarray(self.cv2.cvtColor(self.frame, self.cv2.COLOR_BGR2RGB))
        box = self.det.box
        bottle = bottle_image(full, box, self.detector.roi, self.vcfg.get("crop_mode", "box"),
                              self.vcfg.get("crop_margin", 0.2))
        return full, bottle, box

    def classify(self, bottle: Image.Image) -> tuple[str, float, dict]:
        if self._clf is None:   # 처음 판정할 때 불러온다. 가중치가 없으면 예외 → app이 재검사(RE)로 처리
            self._clf = load_classifier(self.vcfg)
        return self._clf.predict_image(bottle)

    def preview_jpeg(self, text: str = "") -> bytes:
        cv2 = self.cv2
        show = self.frame.copy()
        roi = self.detector.roi
        if roi:
            cv2.rectangle(show, (roi[0], roi[1]), (roi[2], roi[3]), (0, 255, 255), 3)
        if self.det.box:
            x, y, w, h = self.det.box
            color = (0, 255, 0) if self.det.status == "INSIDE" else (255, 200, 0)
            cv2.rectangle(show, (x, y), (x + w, y + h), color, 3)
        scale = PREVIEW_WIDTH / show.shape[1]
        if scale < 1:
            show = cv2.resize(show, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if text:
            cv2.putText(show, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
            cv2.putText(show, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        ok, buf = cv2.imencode(".jpg", show, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else b""

    def close(self) -> None:
        self.cap.release()
