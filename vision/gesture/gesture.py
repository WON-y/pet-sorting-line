"""손가락 수 → 운전 모드 번호 (R6). 정지에는 쓰지 않는다 (safety_rules.md 1절 5항).

규칙 (modes_and_states.md 1절과 같아야 함):
  손가락 1개 → 모드 1(자동, 재가동 확인용), 2개 → 모드 2(저속), 4개 → 모드 4(점검 잠금)
  그 밖의 손가락 수는 무시.
"""
from __future__ import annotations

from collections import deque

FINGERS_TO_MODE = {1: 1, 2: 2, 4: 4}


class GestureConfirmer:
    """같은 손짓이 confirm_frames번 연속으로 보여야 모드를 확정한다."""

    def __init__(self, confirm_frames: int = 10):
        self.n = confirm_frames
        self.buf: deque[int | None] = deque(maxlen=confirm_frames)
        self.last_confirmed: int | None = None

    def update(self, fingers: int | None) -> int | None:
        """이번 프레임의 손가락 수를 넣으면, 새로 확정된 모드 번호를 돌려준다(없으면 None)."""
        self.buf.append(FINGERS_TO_MODE.get(fingers) if fingers is not None else None)
        if len(self.buf) == self.n and len(set(self.buf)) == 1 and self.buf[0] is not None:
            if self.buf[0] != self.last_confirmed:
                self.last_confirmed = self.buf[0]
                return self.last_confirmed
        if len(self.buf) == self.n and all(v is None for v in self.buf):
            self.last_confirmed = None  # 손을 치우면 같은 손짓을 다시 받을 수 있음
        return None


def count_fingers(hand_landmarks) -> int:
    """MediaPipe 손 랜드마크로 펴진 손가락 수를 센다. TODO: 엄지 방향·왼손/오른손 처리 (vision/gesture/README.md)."""
    tips, pips = [8, 12, 16, 20], [6, 10, 14, 18]
    lm = hand_landmarks.landmark
    return sum(1 for t, p in zip(tips, pips, strict=True) if lm[t].y < lm[p].y)
