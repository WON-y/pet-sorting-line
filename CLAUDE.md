# CLAUDE.md — 이 저장소에서 작업하는 AI 도우미를 위한 안내

이 파일은 VS Code의 Claude가 작업을 시작할 때 가장 먼저 읽는 문서입니다. 사람 팀원도 같이 읽어 주세요.

## 프로젝트 한 줄 요약

컨베이어 위 페트병을 웹캠 + YOLO로 판정하고, AIHand(micro:bit 로봇 손) 2대가 날개판으로 분기하며, 신호 손 2대가 작업 지시(숫자 카드·손짓)와 위험 상태를 전달한다. 사람이 다가오면 경고하고, 정지 거리에 들어오면 반드시 멈춘다.

## 작업 전에 반드시 읽을 것 (순서대로)

1. `docs/spec/safety_rules.md` — 안전 규칙. 다른 모든 규칙보다 우선한다.
2. `docs/spec/architecture.md` — 모듈, 실행 위치, 컨테이너.
3. 작업과 관련된 규격:
   - 메시지·핀·MQTT·API → `docs/spec/protocol.md`
   - 모드·우선순위·판정 클래스·상태 머신 → `docs/spec/modes_and_states.md`
   - DB·manifest·전처리 → `docs/spec/data_and_logging.md`
   - 설정 키 → `docs/spec/config.md`
   - 코딩·Git 규칙 → `docs/spec/conventions.md`
4. 작업할 폴더의 `README.md` (도커 컨테이너는 `CONTAINER.md`도).
5. 요구사항·KPI 정의 → `docs/PRD.md`

## 꼭 지킬 규칙

- **규격이 기준이다.** 메시지, 모드 번호, 클래스, 핀, 토픽을 새로 만들거나 바꾸지 말고 규격에 있는 것을 쓴다. 규격에 없는 것이 필요하면, 코드를 쓰기 전에 사람에게 "규격 변경 제안"으로 먼저 알린다.
- 규격을 바꾸기로 했다면 같은 작업 안에서 `docs/spec/…` → `common/protocol.py` → `tests/` 순서로 함께 고친다.
- **안전 경로에 노트북·도커·MQTT·YOLO·손짓 인식을 넣지 않는다.** 정지는 센서와 전선으로만 한다.
- `safety/` 코드나 정지·하트비트 관련 부분을 고쳤으면, 사람이 정지 시험(N1~N5)을 하기 전까지 "완료"라고 하지 않는다. 고친 내용과 사람이 해야 할 시험을 목록으로 남긴다.
- 숫자 설정값은 코드에 직접 쓰지 않고 `config/settings.yaml` + `common/config.py`를 쓴다.
- 메시지 문자열은 `common/protocol.py`의 함수로 만들고 해석한다.
- 파이썬 코드는 하드웨어 없이 `pytest`가 돌아가야 한다. 하드웨어 부분은 모의 객체를 쓴다.
- 커밋 메시지와 브랜치 이름에 요구사항 ID를 넣는다 (예: `[R4] …`, `feat/R4-…`).
- 개인정보(연락처·주소), 사람 얼굴·손 사진, 학습 이미지, `.env`는 커밋하지 않는다.
- 문서와 주석은 한국어로 쓴다.

## 자주 쓰는 명령

```bash
pip install -r requirements-dev.txt      # 시험·모의 실행용 (가벼움)
pip install -r requirements-hw.txt       # 실제 하드웨어 실행용 (웹캠·YOLO·MediaPipe)
pytest                                   # 시험 (하드웨어 없이)
ruff check .                             # 스타일 검사
python -m app --mock                     # 하드웨어 없이 모의 실행 (라인 + 대시보드 http://localhost:8000)
python -m app                            # 웹캠 + YOLO 통합 실행 (우노 포트 없으면 가상 벨트)
docker compose up -d                     # (선택) 도커로 mqtt + dashboard 따로
```

## 폴더 지도

| 폴더 | 내용 |
| --- | --- |
| `docs/` | PRD, 규격(spec), 배선도, 시험 기록 |
| `config/` | settings.yaml |
| `common/` | 규격을 코드로 옮긴 공통 모듈 (protocol, config) |
| `hardware/` | 손 1~4 micro:bit 프로그램 (MakeCode) |
| `safety/` | 아두이노 벨트·안전 펌웨어 (통합본, 우노에 올리는 것) |
| `code/` | 제어 담당이 만든 micro:bit 프로그램 (`code/CLAUDE.md`), 예전 벨트 펌웨어(참고용) |
| `vision/` | bottle(YOLO 판정), card(WonderCam 안내), gesture(MediaPipe) |
| `communication/` | 게이트웨이 micro:bit, 노트북 시리얼 연결 |
| `app/` | 노트북 통합 실행(상태 머신, 가상 벨트, 대시보드 같이 띄움), 모의 모드 |
| `dashboard/` | 웹 대시보드 (FastAPI + SQLite, app 안에서 실행. 도커는 선택) |
| `infra/mqtt/` | MQTT 브로커 컨테이너 |
| `training/` | 학습 노트북, manifest, 가중치 |
| `tests/` | pytest 시험 |
