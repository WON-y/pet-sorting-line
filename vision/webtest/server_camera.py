"""노트북에 꽂은 USB 웹캠을 서버(OpenCV)가 직접 읽는다.

실제 라인(`vision/bottle/camera.py`)과 같은 방식이라 브라우저 카메라 권한이 필요 없다.
카메라는 한 번에 하나만 열고, 번호를 바꾸면 이전 카메라를 닫는다.
"""
from __future__ import annotations

import io
import threading

from PIL import Image

JPEG_QUALITY = 85


def open_opencv_camera(index: int):
    from vision.bottle.camera import Camera  # cv2는 사용할 때만 import

    return Camera(index)


class ServerCamera:
    def __init__(self, opener=open_opencv_camera):
        self.opener = opener
        self.index: int | None = None
        self.cam = None
        self.lock = threading.Lock()

    def _ensure(self, index: int):
        if self.cam is not None and self.index == index:
            return self.cam
        self._release()
        self.cam = self.opener(index)   # 열 수 없으면 RuntimeError
        self.index = index
        return self.cam

    def _release(self) -> None:
        if self.cam is not None and hasattr(self.cam, "cap"):
            self.cam.cap.release()
        self.cam, self.index = None, None

    def frame_jpeg(self, index: int) -> bytes:
        with self.lock:
            try:
                rgb = self._ensure(index).read_rgb()
            except Exception:
                self._release()   # 뽑혔거나 다른 프로그램이 쓰는 중 → 다음 요청 때 다시 연다
                raise
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, "JPEG", quality=JPEG_QUALITY)
        return buf.getvalue()

    def close(self) -> None:
        with self.lock:
            self._release()
