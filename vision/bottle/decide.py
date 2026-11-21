"""프레임 판정 결과로 판정 코드를 정한다 (docs/spec/modes_and_states.md 4절).

기본은 벨트가 멈춘 뒤 1프레임(`vision.frames: 1`). 여러 프레임을 주면 모두 같아야 확정한다.
"""
from __future__ import annotations

from collections import Counter

from common.protocol import CLASS_TO_CODE, RECHECK


def decide(preds: list[tuple[str, float]], frames: int = 1, conf_threshold: float = 0.6) -> tuple[str, str]:
    """preds: [(클래스, 신뢰도), ...] 최근 프레임.

    반환: (대표 클래스, 판정 코드). 프레임 없음·부족·불일치·신뢰도 미달이면 코드 'RE'.
    """
    if len(preds) < frames:
        return (preds[0][0] if preds else "", RECHECK)
    recent = preds[-frames:]
    top, count = Counter(c for c, _ in recent).most_common(1)[0]
    if count == frames and min(conf for _, conf in recent) >= conf_threshold and top in CLASS_TO_CODE:
        return top, CLASS_TO_CODE[top]
    return top, RECHECK
