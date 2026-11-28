# 데이터·기록 규격

## 1. 이벤트 기록 (SQLite, dashboard 컨테이너)

DB 파일: `data/logs/pet.db` (`dashboard.db_path`). 기본은 노트북 `python -m app` 한 프로그램 안에서 대시보드 모듈(`dashboard/app/store.py`)이 저장한다. 도커로 띄울 때만 dashboard가 MQTT를 구독해 저장한다. 모의 실행(`--mock`)은 `data/mock/pet.db`, `data/mock/captures/`에 따로 저장한다.
나중에 Supabase로 옮길 때는 `Store`와 같은 메서드를 가진 저장 클래스를 추가해 바꿔 끼운다 (테이블은 아래 두 개, 사진은 Storage 버킷).

```sql
CREATE TABLE events (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       TEXT NOT NULL,      -- ISO 8601, KST
  topic    TEXT NOT NULL,      -- pet/judgment, pet/safety ...
  type     TEXT NOT NULL,      -- JUDGMENT, SORT, MODE, HAND, WARN, STOP, RUN, CLEAR, ERROR
  bottle   INTEGER,            -- 병 id (해당될 때)
  payload  TEXT NOT NULL       -- 받은 JSON 그대로
);
CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_events_type ON events(type);
```

```sql
-- 판정 사진 (재학습용). JUDGMENT 이벤트에 img가 있으면 함께 들어간다
CREATE TABLE captures (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER,            -- events.id
  ts       TEXT NOT NULL,
  bottle   INTEGER,
  img      TEXT NOT NULL,      -- 병 사진 (사진 폴더 기준 경로)
  full     TEXT,               -- 전체 화면 사진
  pred_cls TEXT, conf REAL, code TEXT, trigger TEXT,
  label    TEXT NOT NULL DEFAULT ''   -- 사람이 확인한 정답: 4클래스 / exclude / '' (미확인)
);
```

- `pet/state`는 화면 표시용이라 저장하지 않는다(최신 값만 메모리).
- 아차사고(선택 S8) = `type IN ('WARN','STOP')` 집계로 계산한다. 따로 테이블을 만들지 않는다.

## 2. 대시보드 집계 정의

| 항목 | 계산 |
| --- | --- |
| 통별 개수 | `JUDGMENT`의 code별 개수 (OK·CO·NG·RE) |
| 재검사 비율 (N11) | RE 수 / JUDGMENT 수 |
| 정지 횟수 | `STOP` 수, cause별 |
| 아차사고 | `WARN` + `STOP` 수, 시간대별 |
| 모드 변경 기록 | `MODE` 목록 |

## 3. 학습 데이터 (training)

- 원본 이미지는 **깃허브에 올리지 않는다.** 팀 공유 드라이브에 둔다.
- 깃허브에는 `training/manifest.csv`(정답 기준표)와 출처·라이선스 목록만 올린다.

`manifest.csv` 열:

| 열 | 뜻 | 값 |
| --- | --- | --- |
| `file` | 파일 이름 | `P_B07_003.jpg` |
| `group` | 같은 병 묶음 (분할 단위) | `B07` |
| `source` | 출처 | `phone` / `belt` / `online:aihub` / `online:roboflow:<데이터셋>` |
| `license` | 라이선스 (재배포 가능 여부 포함) | `CC0`, `CC BY 4.0`, `aihub`(재배포 불가), `team` 등 |
| `is_pet` | 페트병인가 | 1/0 |
| `is_clear` | 무색투명인가 | 1/0 |
| `has_label` | 라벨이 있는가 | 1/0 |
| `has_content` | 내용물이 남았는가 (기록용, 클래스에 쓰지 않음) | 1/0 |
| `split` | 분할 | `train`/`val`/`test` |
| `removed` | 제외 이유 | 빈칸 또는 `blur`/`crop`/`dup`/`review` |

- 학습 폴더(`dataset/train/<class>/`)는 이 표에서 스크립트로 만든다. 클래스 규칙은 `modes_and_states.md` 4절.
- 분할은 `group` 단위. 같은 병이 train과 val·test에 함께 들어가면 안 된다 (벨트 사진도 같은 병끼리 묶는다).
- 학습 데이터: AI Hub·Roboflow 이미지를 전처리해 쓰고, 재료 도착 후 시연 조명·카메라 그대로 찍은 벨트 사진(`W`)으로 미세조정한다.
- **최종 평가(N10·N11)는 벨트 사진(`source=belt`)으로만** 한다.
- 재배포가 제한된 이미지(AI Hub 등)는 저장소에 올리지 않는다. 출처·라이선스는 manifest에 반드시 적는다.
- 파일 이름 규칙: `출처_병번호_순번.jpg` (출처 `P` 휴대폰, `W` 벨트 웹캠, `O` 온라인). 한글·공백 금지.

### 벨트 촬영 사진 (자동 저장)

- 라인이 판정할 때마다 `vision.capture_dir`(기본 `data/captures/`)에 날짜 폴더로 저장한다: `YYYYMMDD/W_YYYYMMDD-HHMMSS_<병id>_crop.jpg`(병 사진, 레터박스 전) + `..._full.jpg`(전체 화면). 깃허브에 올리지 않는다(`.gitignore`).
- 병 번호를 모르므로 시각과 app 병 id를 이름에 쓴다. `group`(같은 병 묶음)은 사람이 정리할 때 채운다.
- 대시보드 "촬영 사진"에서 정답을 고르면 `captures.label`에 저장되고, `/api/captures.csv`로 manifest와 같은 열의 목록을 받는다(`source=belt`, `license=team`). 학습에서 뺄 사진은 `exclude` → `removed=review`.

## 4. 사진 전처리 규칙 (학습·판정 공통)

- 판정 구역(ROI)만 자른다: `vision.roi`. 웹캠 감지로 병 박스를 찾았으면 박스 둘레 정사각형(`vision.crop_margin`)을 자른다(`vision.crop_mode: box`, `preprocess.crop_box`). 온라인 학습 사진(병 둘레로 자른 사진)과 구도를 맞추기 위해서다.
- 비율 유지 + 224×224 회색 레터박스: `vision.letterbox_color`.
- 학습과 판정은 **같은 함수**(`vision/bottle/preprocess.py`)를 쓴다.
- 색이 정답 정보이므로 색조 증강 금지(`hsv_h=0`), RandAugment·무작위 지우기(`erasing=0`) 금지.

## 5. 올리면 안 되는 것

- 사람 얼굴·손이 나온 사진과 영상 (손짓 데이터 포함)
- 연락처·주소가 들어간 문서 (재료 신청서 등)
- `data/logs/`, `runs/`, 학습 이미지, `.env`
