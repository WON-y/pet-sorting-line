# 컨테이너: dashboard

> **2026-11-26부터 기본은 도커 없이** `python -m app`이 이 대시보드를 같은 프로그램 안에서 띄운다 (`app/README.md`).
> 이 컨테이너는 대시보드를 다른 컴퓨터에서 따로 띄우거나 CI 도커 시험을 할 때만 쓴다. 이때 실시간 화면·시험 버튼(`/api/line`)은 없고(503), 사진은 `data/captures`를 볼륨으로 연결해야 보인다.

## 역할

- MQTT 브로커(`mqtt` 컨테이너)의 `pet/#` 토픽을 구독해 이벤트를 SQLite에 저장한다.
- 저장한 기록을 집계해 HTTP API와 웹 화면으로 보여준다 (R8, KPI N14).
- **기록과 표시만 한다.** 라인을 제어하지 않고, 정지 경로에도 들어가지 않는다. 이 컨테이너가 꺼져도 라인은 돈다.

## 도커 정보

| 항목 | 값 |
| --- | --- |
| 이미지 | `dashboard/Dockerfile` (python:3.12-slim + FastAPI + uvicorn + paho-mqtt) |
| 포트 | 8000 → 브라우저 `http://localhost:8000` |
| 볼륨 | `./data/logs` → `/data` (DB 파일 `pet.db`, 컨테이너를 지워도 남음) |
| 환경 변수 | `MQTT_HOST`(mqtt), `MQTT_PORT`(1883), `DB_PATH`(/data/pet.db), `DISABLE_MQTT`(시험용 1) |
| 의존 | `mqtt` |

## 파일

| 파일 | 내용 |
| --- | --- |
| `app/main.py` | FastAPI 앱, MQTT 구독, API 경로 |
| `app/store.py` | SQLite 스키마·저장·집계 (`docs/spec/data_and_logging.md`) |
| `static/index.html` | 대시보드 화면 (2초마다 API 조회) |

## API (규격: `docs/spec/protocol.md` 6절)

`GET /health`, `GET /api/summary`, `GET /api/events?type=&limit=`, `GET /`

## 실행

```bash
docker compose up -d dashboard           # mqtt도 같이 켜짐
docker compose logs -f dashboard         # 로그 보기
# 도커 없이 개발할 때 (저장소 루트에서)
pip install -r dashboard/requirements.txt
DB_PATH=data/logs/pet.db uvicorn dashboard.app.main:app --reload
```

## 작업 규칙

- 새 토픽·이벤트 종류는 규격(`protocol.md` 5절, `data_and_logging.md` 1절)에 먼저 추가한다.
- DB 스키마를 바꾸면 기존 `pet.db`와 맞지 않을 수 있다. 바꿀 때는 `data/logs/pet.db`를 지우고 다시 만드는 방법을 README에 적는다.
- 화면은 정적 HTML/JS 하나로 유지한다(빌드 도구 없음). 외부 CDN은 시연장 인터넷이 없을 수 있어 쓰지 않는다.
- 시험: `tests/test_dashboard.py` (MQTT 없이 `handle_message`로 저장·집계 확인).
