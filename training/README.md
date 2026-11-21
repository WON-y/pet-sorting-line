# 학습

- 실행 위치: Google Colab (무료 T4), 도커 아님
- 원본 이미지는 깃허브에 올리지 않는다 → 팀 공유 드라이브. 여기에는 정답표·노트북·가중치만.

| 파일 | 내용 |
| --- | --- |
| `pet_cls_train.ipynb` | 학습 노트북 (실험 A/B, 클래스별 평가, 판정 함수) |
| `manifest.csv` | 정답 기준표 (열 정의: `docs/spec/data_and_logging.md` 3절) — 팀이 채움 |
| `weights/best.pt` | 현재 사용하는 가중치 (3MB 정도, 커지면 Releases로) |

## 규칙

- 전처리는 `vision/bottle/preprocess.py`와 같아야 한다 (회색 값, 레터박스 방식).
- 분할은 `group`(같은 병) 단위.
- 색조 증강·RandAugment·무작위 지우기 금지.
- 클래스를 늘리면 `docs/spec/modes_and_states.md` 4절과 `common/protocol.CLASS_TO_CODE`를 같이 고친다.
- 결과(클래스별 재현율, 혼동행렬)는 `docs/tests/kpi_log.md`의 N10·N11에 기록.

## 모델 선택

- YOLO 분류 모델 여러 개(크기·버전이 다른 모델, 예: `yolo11n/s-cls`, `yolov8n/s-cls`)를 **같은 데이터·같은 평가 기준**으로 학습해 가장 좋은 모델을 고른다.
- 평가 기준: 클래스당 정확도 ≥ 90%, 재검사 비율 ≤ 10%, `clear_label` → `clear_nolabel`(라벨 있는 투명 병을 적합으로 통과) 0회.
- YOLO 외의 모델은 시간이 남으면 비교한다.
- 재료 도착 후 벨트 사진으로 미세조정하고, 최종 평가는 벨트 사진으로만 한다.

## 할 일

- [ ] 노트북에 여러 모델 비교 실험 추가 (지금은 `yolo11n-cls`만)
