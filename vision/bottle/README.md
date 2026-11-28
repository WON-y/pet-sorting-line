# 비전: 페트병 판정 (R4)

- 실행 위치: 노트북 (도커 아님, 웹캠 때문)
- 카메라: USB 웹캠 Coms TB591 (1080p, LED 조명 내장), 클램프 스탠드 + 매직암으로 벨트 위 30~40cm에 고정, 수직으로 내려찍음
- 모델: Ultralytics YOLO 분류 모델(사진 전체 분류, 탐지 아님), 입력 224×224. 여러 모델을 비교해 고른다 → `training/README.md`
- 모델 2개: **색 모델**(clear/color) + **라벨 모델**(label/nolabel) → 합쳐서 4클래스 (`classifier.py`의 `combine`)
- 가중치: `training/weights/color_best.pt`, `label_best.pt` (`settings.yaml: vision.color_model`, `vision.label_model`). 파일이 없으면 모두 재검사(RE). 예전 4클래스 `best.pt`는 `vision.model_mode: single`
- WonderCam에는 직접 학습한 모델을 올릴 방법이 문서에 없어, 판정은 노트북에서 한다.

## 흐름

웹캠 도착 감지(빈 벨트 기준과 비교, 병이 판정 구역 안에 완전히 들어옴) → **벨트를 멈추지 않고 그 프레임** 촬영 → 병 둘레 자르기(`crop_mode: box`) + 224×224 회색 레터박스 → 4클래스 분류 → 신뢰도 ≥ 0.6이면 확정, 아니면 `RE`(재검사 → 부적합 슈트) → 사진 저장(`data/captures/`)

- IR 도착 센서는 나중에 보조로 쓴다 (우노 `USE_IR_ARRIVE`, `EVT,ARRIVE`).
- 감지는 카메라가 **고정**돼 있어야 한다. 손으로 든 휴대폰 영상은 화면 전체가 움직여 계속 "가장자리에 걸침"이 된다.

- 벨트가 움직이는 채로 찍는다 (`app.stop_to_judge: false`). 사진이 흐리면 조명을 밝게 하거나(웹캠 노출 시간이 짧아짐) `vision.frames`를 3으로 올려 여러 장으로 판정한다. 예전처럼 멈추고 찍으려면 `app.stop_to_judge: true`.
- 4클래스와 2단계 분기(손 1: 유색 → 기타, 손 2: 투명·라벨 → 부적합)는 `docs/spec/modes_and_states.md` 4절.
- 병마다 4클래스 이름·판정 코드·신뢰도·시각을 `pet/judgment`로 대시보드에 기록한다.

## 파일

| 파일 | 내용 |
| --- | --- |
| `preprocess.py` | `crop_roi`, `letterbox`, `prepare` — **학습과 판정이 같이 쓰는 전처리** |
| `classifier.py` | `SplitClassifier`(색 + 라벨 모델), `BottleClassifier`(4클래스 하나), `load_classifier`, `combine` (ultralytics는 사용할 때만 import) |
| `decide.py` | 신뢰도 기준 판정 규칙 → (클래스, 판정 코드). 기본 1프레임 |
| `camera.py` | OpenCV 웹캠 읽기 (RGB) |
| `detect.py` | 웹캠 병 도착 감지 (`ArrivalDetector`, 하드웨어 없이 시험하는 `StreakCounter`) |
| `pipeline.py` | `CameraVision` — 웹캠·녹화 영상 → 감지 → 촬영 → 판정 → 대시보드 미리보기 (app이 사용) |
| `phone.py` | `PhoneVision` — 웹캠 대신 휴대폰 카메라 사진으로 같은 일 (`python -m app --phone`, `app/README.md`) |

## 규칙

- 클래스·코드 대응은 `docs/spec/modes_and_states.md` 4절, `common/protocol.CLASS_TO_CODE`.
- `letterbox_color`와 `roi`는 `settings.yaml`에서만 바꾼다. 학습 때와 다르면 정확도가 떨어진다.
- 촬영 환경: 판정 구역 둘레에 가림막을 세우고, 정면 조명과 측면 조명을 비교해 하나로 고정한다.
- 카메라 높이·각도·노출·조명을 바꾸면 다시 학습(미세조정)한다.
- 색이 정답 정보이므로 색조 변경·무작위 지우기 증강은 쓰지 않는다.
- 시험: `tests/test_vision.py` (모델 없이 전처리·판정 규칙 확인)

## 성능 목표 (벨트 위 사진으로만 평가)

| 지표 | 목표 | KPI |
| --- | --- | --- |
| 클래스당 정확도 | 90% 이상 | N10 |
| 라벨 있는 투명 병을 적합으로 통과 | 0회 | N10 |
| 재검사 비율 | 10% 이하 | N11 |

## 예비 경로

YOLO가 목표에 못 미치면 WonderCam 색 인식으로 **투명/유색 2분류만** 시연한다(라벨 판정 없음).

## 할 일

- [ ] 벨트 설치 후 `vision.roi` 정하기
- [ ] 가림막 설치, 정면 조명 vs 측면 조명 50장 비교 후 고정
- [ ] 벨트 데이터로 미세조정(v1), 같은 병은 학습/평가에 섞지 않기, 평가는 벨트 사진으로만 (N10, N11)
