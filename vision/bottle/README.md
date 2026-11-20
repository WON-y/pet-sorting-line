# 비전: 페트병 판정 (R4)

- 실행 위치: 노트북 (도커 아님, 웹캠 때문)
- 모델: Ultralytics YOLO11n-cls, 입력 224×224
- 가중치: `training/weights/best.pt` (`settings.yaml: vision.weights`)

## 흐름

IR 도착 → 벨트 멈춤 → 웹캠 3프레임 → 판정 구역 자르기 + 회색 레터박스 → 분류 → 3프레임 일치·신뢰도 ≥ 0.6이면 확정, 아니면 `RE`

## 파일

| 파일 | 내용 |
| --- | --- |
| `preprocess.py` | `crop_roi`, `letterbox`, `prepare` — **학습과 판정이 같이 쓰는 전처리** |
| `classifier.py` | `BottleClassifier` (ultralytics는 사용할 때만 import) |
| `decide.py` | 연속 프레임 확정 규칙 → (클래스, 판정 코드) |
| `camera.py` | OpenCV 웹캠 읽기 (RGB) |

## 규칙

- 클래스·코드 대응은 `docs/spec/modes_and_states.md` 4절, `common/protocol.CLASS_TO_CODE`.
- `letterbox_color`와 `roi`는 `settings.yaml`에서만 바꾼다. 학습 때와 다르면 정확도가 떨어진다.
- 카메라 높이·각도·노출·조명을 바꾸면 다시 학습(미세조정)한다.
- 시험: `tests/test_vision.py` (모델 없이 전처리·확정 규칙 확인)

## 할 일

- [ ] 벨트 설치 후 `vision.roi` 정하기
- [ ] 정면 조명 vs 측면 조명 50장 비교
- [ ] 벨트 데이터로 미세조정(v1), 평가는 벨트 사진으로만 (N10, N11)
