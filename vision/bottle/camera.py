"""웹캠 읽기 (OpenCV). 노출·초점은 고정해 두는 것을 권장 (vision/bottle/README.md)."""
from __future__ import annotations


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720):
        import cv2

        self.cv2 = cv2
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            raise RuntimeError(f"웹캠 {index}번을 열 수 없습니다")

    def read_rgb(self):
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("웹캠 프레임을 읽지 못했습니다")
        return self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
