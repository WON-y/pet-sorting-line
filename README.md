# pet-sorting-line

투명 페트병 선별 라인의 신호 전달과 안전 — 3팀 프로젝트

AI가 컨베이어 위 페트병을 배출 기준대로 판정하고(투명 적합 / 부적합 / 기타), AIHand 작업 손 2대가 날개판으로 병을 가릅니다. 작업자는 숫자 카드나 손짓으로 라인에 지시하고, 신호 손 2대가 그 지시와 위험 상태를 손 모양·빛·소리로 전달합니다. 사람이 다가오면 늦추고, 손이 벨트 위에 들어가면 반드시 멈춥니다.

## 기능 구성

| 기능          | 내용                                                     | 폴더               |
| ------------- | -------------------------------------------------------- | ------------------ |
| 하드웨어 제어 | 작업 손 날개판 분기, 신호 손 표시                        | `hardware/`      |
| 안전          | 벨트 구동, IR 커튼, 하트비트, 리셋                       | `safety/`        |
| 비전          | 페트병 판정(YOLO), 숫자 카드(WonderCam), 손짓(MediaPipe) | `vision/`        |
| 통신          | micro:bit 라디오 게이트웨이, 시리얼·MQTT 연결           | `communication/` |
| 통합 실행     | 노트북 상태 머신, 모의 모드                              | `app/`           |
| 웹 대시보드   | 통별 개수, 재검사, 정지·아차사고 기록                   | `dashboard/`     |

자세한 구조는 [`docs/spec/architecture.md`](docs/spec/architecture.md), 요구사항은 [`docs/PRD.md`](docs/PRD.md).

## 빠른 시작

```bash
# 1) 대시보드와 MQTT (도커)
cp .env.example .env
docker compose up -d
# 브라우저: http://localhost:8000

# 2) 하드웨어 없이 전체 흐름 보기
docker compose --profile mock up

# 3) 노트북 파이썬 환경 (실제 하드웨어: 웹캠·YOLO·MediaPipe 포함)
pip install -r requirements-hw.txt
python -m app            # .env에 GATEWAY_PORT, ARDUINO_PORT 설정
```

## 규격 문서 (작업 전에 읽기)

| 문서                                                | 내용                                        |
| --------------------------------------------------- | ------------------------------------------- |
| [safety_rules.md](docs/spec/safety_rules.md)         | 안전 규칙 (최우선)                          |
| [protocol.md](docs/spec/protocol.md)                 | 라디오·시리얼·핀·MQTT·API 메시지        |
| [modes_and_states.md](docs/spec/modes_and_states.md) | 운전 모드, 우선순위, 판정 클래스, 상태 머신 |
| [data_and_logging.md](docs/spec/data_and_logging.md) | DB, manifest, 전처리 규칙                   |
| [config.md](docs/spec/config.md)                     | 설정 키                                     |
| [conventions.md](docs/spec/conventions.md)           | 코딩·Git 규칙                              |

AI 도구(Claude 등)로 작업할 때는 [`CLAUDE.md`](CLAUDE.md)를 먼저 읽게 하세요.
