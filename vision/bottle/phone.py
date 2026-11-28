"""휴대폰 카메라를 웹캠 대신 쓰기 (python -m app --phone).

휴대폰 브라우저가 https 페이지(app/phone_server.py)에서 카메라 사진(JPEG)을 계속 보내면,
PhoneFeed가 가장 최근 한 장을 들고 있고, PhoneVision이 그것을 웹캠 프레임처럼 읽는다.
PhoneVision은 CameraVision과 같은 메서드를 가진다 (grab, capture, classify, preview_jpeg, ...).

정지 경로가 아니다. 판정을 위해 벨트를 잠깐 세우는 용도다 (안전 정지는 우노·센서·전선).
휴대폰이 끊기면 도착·비었음 신호를 내지 않는다 (벨트를 세우지도, 다음 병을 받지도 않음).
"""
from __future__ import annotations

import logging
import secrets
import threading
import time

from PIL import Image

from .detect import ArrivalDetector, Detection
from .pipeline import CameraVision

log = logging.getLogger(__name__)
MAX_FRAME_BYTES = 5 * 1024 * 1024     # 사진 한 장 최대 크기 (이보다 크면 받지 않음)


class PhoneFeed:
    """휴대폰이 보낸 가장 최근 JPEG 한 장 (웹 서버 스레드가 넣고, 라인 루프가 읽음). cv2 없이 동작."""

    def __init__(self, timeout_ms: int = 2000, token: str | None = None):
        self.token = token or secrets.token_urlsafe(9)   # QR 주소에 넣어 다른 기기가 사진을 못 넣게
        self.timeout_s = timeout_ms / 1000
        self.urls: list[str] = []                          # 휴대폰 접속 주소 (app/main.py가 채움)
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None
        self._seq = 0
        self._at = 0.0

    def check(self, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(str(token), self.token)

    def push(self, jpeg: bytes) -> int:
        if not jpeg.startswith(b"\xff\xd8"):
            raise ValueError("JPEG 사진이 아닙니다")
        if len(jpeg) > MAX_FRAME_BYTES:
            raise ValueError("사진이 너무 큽니다")
        with self._lock:
            self._jpeg, self._seq, self._at = jpeg, self._seq + 1, time.monotonic()
            return self._seq

    def latest(self) -> tuple[int, bytes | None]:
        with self._lock:
            return self._seq, self._jpeg

    def connected(self) -> bool:
        return self._seq > 0 and time.monotonic() - self._at < self.timeout_s

    def info(self) -> dict:
        age = round((time.monotonic() - self._at) * 1000) if self._seq else None
        return {"urls": self.urls, "connected": self.connected(), "frames": self._seq, "age_ms": age}


class PhoneVision(CameraVision):
    """CameraVision과 같은 모양. 프레임만 웹캠 대신 PhoneFeed에서 가져온다."""

    def __init__(self, vcfg: dict, feed: PhoneFeed):
        import cv2
        import numpy as np

        self.cv2, self.np = cv2, np
        self.vcfg = vcfg
        self.feed = feed
        self.source = "phone"
        self.is_file = False
        self.detector = ArrivalDetector.from_config(vcfg)
        w, h = vcfg.get("camera_size", [1280, 720])
        self.frame = np.zeros((int(h), int(w), 3), np.uint8)   # 휴대폰이 붙기 전 빈 화면
        self.has_frame = False
        self.det = Detection("NO_BASELINE")
        self._clf = None
        self._seq = 0
        log.info("영상 입력: 휴대폰 카메라 (대시보드의 QR로 접속)")

    # ---- 입력 ----
    def grab(self, belt_moving: bool = True) -> Detection:
        """새 사진이 왔을 때만 감지를 돌린다 (같은 사진으로 연속 프레임 수가 부풀지 않게)."""
        seq, jpeg = self.feed.latest()
        if seq != self._seq and jpeg is not None:
            self._seq = seq
            frame = self.cv2.imdecode(self.np.frombuffer(jpeg, self.np.uint8), self.cv2.IMREAD_COLOR)
            if frame is not None:
                self.frame, self.has_frame = frame, True
                self.det = self.detector.update(frame)
        if not self.feed.connected():          # 끊김: 마지막 상태는 보여 주되 도착·비었음 신호는 내지 않음
            return Detection(self.det.status, self.det.box)
        return self.det

    # ---- 설정 ----
    def set_baseline(self, moving: bool = False) -> None:
        if not self.feed.connected():
            raise ValueError("휴대폰 카메라가 연결되지 않았습니다 (대시보드 QR로 접속)")
        super().set_baseline(moving)

    def info(self) -> dict:
        return super().info() | {"phone": self.feed.info()}

    # ---- 촬영·판정 ----
    def capture(self) -> tuple[Image.Image, Image.Image, tuple | None]:
        if not self.feed.connected():
            raise RuntimeError("휴대폰 카메라가 연결되지 않았습니다")
        return super().capture()

    def preview_jpeg(self, text: str = "") -> bytes:
        if not self.has_frame:
            text = "phone: waiting (scan QR on dashboard)"
        elif not self.feed.connected():
            text = "phone: DISCONNECTED | " + text
        return super().preview_jpeg(text)

    def close(self) -> None:
        pass
