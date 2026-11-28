# 시스템 구조

## 1. 기능별 모듈과 실행 위치

| 기능 | 폴더 | 실행 위치 | 언어 | 도커 |
| --- | --- | --- | --- | --- |
| 하드웨어 제어: 작업 손 분기 | `hardware/hand1_sorter`, `hand2_sorter` | 손 1·2 micro:bit | MakeCode | 아니오 |
| 하드웨어 제어: 신호 손 | `hardware/hand3_signal`, `hand4_remote` | 손 3·4 micro:bit | MakeCode | 아니오 |
| 안전·벨트 | `safety/belt_controller` | 아두이노 우노 | Arduino C++ | 아니오 |
| 비전: 페트병 판정 | `vision/bottle` | 노트북 | Python (YOLO) | 아니오 (웹캠) |
| 비전: 숫자 카드 | `vision/card` → 실제 코드는 `hardware/hand3_signal` | 손 3 micro:bit + WonderCam | MakeCode | 아니오 |
| 비전: 손짓 | `vision/gesture` | 노트북 | Python (MediaPipe) | 아니오 (웹캠) |
| 통신: 게이트웨이 | `communication/gateway_microbit` | 게이트웨이 micro:bit | MakeCode | 아니오 |
| 통신: 시리얼·MQTT 연결 | `communication/serial_bridge` | 노트북 | Python | 아니오 (USB) |
| 통합 실행 | `app` | 노트북 | Python | 모의 모드만 |
| 웹 대시보드 | `dashboard` | 노트북 (app 안에서 같이 실행) | Python FastAPI + HTML/JS | 선택 |
| 메시지 브로커 | `infra/mqtt` | 도커 (선택) | mosquitto | 선택 |
| 학습 | `training` | Colab | Python | 아니오 |
| 공통 규격 코드 | `common` | 노트북, 도커 | Python | 포함됨 |

**기본은 도커 없이 노트북 한 프로그램이다 (2026-11-26).** `python -m app`이 웹캠 판정, 상태 머신, 대시보드 웹 서버, SQLite 기록을 함께 돌린다. 웹캠과 USB 시리얼은 윈도우·맥 도커에서 연결이 어렵기 때문에 하드웨어 쪽은 원래 도커에 넣지 않는다.

도커가 필요한 경우 (선택):
- CI의 도커 연동 시험 (`.github/workflows/ci.yml`의 docker 작업)을 유지할 때
- 대시보드를 라인 노트북과 다른 컴퓨터에서 따로 계속 띄워 둘 때 (MQTT로 연결)
- 나중에 Supabase를 **내 컴퓨터에서** 흉내 내 개발할 때 (`supabase start`는 도커 필요). 클라우드 Supabase만 쓰면 도커는 필요 없다.

## 2. 전체 흐름

```
                 ┌──────────────── 노트북: python -m app (한 프로그램) ────────────────┐
웹캠 ──────────▶ │ vision/bottle (도착 감지·판정) ─┐                                    │
웹캠2(선택) ───▶ │ vision/gesture ─────────────────┼─▶ app (상태 머신) ─▶ dashboard ─▶ SQLite + data/captures
게이트웨이 USB ◀▶│ serial_bridge (분기 켤 때) ─────┘      │            (웹 http://localhost:8000)
우노 USB ◀──────▶│                                        └─ 우노 명령(PAUSE, GO, HOLD)   │
                 └─────────────────────────────────────────────────────────────────────┘
게이트웨이 micro:bit ──라디오── 손 1·2·3·4
게이트웨이 ──P0·P1 모드, P2 하트비트──▶ 우노 ◀── 리셋 버튼, (선택) IR 도착     12V ─ 비상정지 ─ 릴레이 ─ TB6600 ─ 벨트
```

## 3. 도커 컨테이너

| 컨테이너 | 폴더 | 역할 | 포트 |
| --- | --- | --- | --- |
| `mqtt` | `infra/mqtt` | 노트북 app과 대시보드 사이 메시지 중계 | 1883 |
| `dashboard` | `dashboard` | MQTT 구독 → SQLite 저장, API와 웹 화면 제공 | 8000 |
| `simulator` (mock 프로필) | `app` | 하드웨어 없이 가짜 병·판정·안전 이벤트를 발행 | 없음 |

각 컨테이너 폴더의 `CONTAINER.md`에 역할과 실행 방법이 있다.

## 4. 실행 순서 (시연)

1. 비상정지 버튼이 눌려 있지 않은지, 바닥 테이프와 IR 커튼 위치 확인
2. 손 1~4, 게이트웨이 micro:bit 전원 켜기
3. 우노 전원 → 켜진 직후는 STOP (잠김)
4. 노트북에서 `python -m app` (우노 포트는 `.env`의 `ARDUINO_PORT`) → 브라우저 `http://localhost:8000`
5. 대시보드에서 판정 구역 그리기
6. 수신호·카드 1 + 리셋 버튼 → 운전 시작 (벨트는 아직 비워 둠)
7. 빈 벨트가 도는 동안 "빈 벨트 기준 만들기" → 약 30초 뒤 "기준 OK" 확인 → 병 넣기 (시연 장소에서 매번 새로 만든다)
