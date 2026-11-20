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
| 웹 대시보드 | `dashboard` | 도커 | Python FastAPI + HTML/JS | 예 |
| 메시지 브로커 | `infra/mqtt` | 도커 | mosquitto | 예 |
| 학습 | `training` | Colab | Python | 아니오 |
| 공통 규격 코드 | `common` | 노트북, 도커 | Python | 포함됨 |

**도커에 넣지 않는 이유:** 웹캠과 USB 시리얼(micro:bit, 우노)은 윈도우·맥 도커에서 연결이 어렵다. 하드웨어를 만지는 프로그램은 노트북에서 직접 실행하고, 결과만 MQTT로 도커에 보낸다.

## 2. 전체 흐름

```
                 ┌──────────────── 노트북 (직접 실행) ────────────────┐
웹캠 ──────────▶ │ vision/bottle ─┐                                   │
웹캠2(선택) ───▶ │ vision/gesture ┼─▶ app (상태 머신) ─▶ MQTT 발행 ───┼──▶ [도커] mqtt ─▶ [도커] dashboard ─▶ SQLite
게이트웨이 USB ◀▶│ serial_bridge ─┘        │                          │
우노 USB ◀──────▶│                         └─ 우노 명령(GO, SPD, ARM)  │
                 └────────────────────────────────────────────────────┘
게이트웨이 micro:bit ──라디오── 손 1·2·3·4
게이트웨이 ──P0·P1──▶ 우노 ◀── IR 커튼·IR 도착·리셋 버튼     12V ─ 비상정지 ─ 릴레이 ─ TB6600 ─ 벨트
           ◀──P2────
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
2. `docker compose up -d` (mqtt, dashboard)
3. 손 1~4, 게이트웨이 micro:bit 전원 켜기 → 모두 `RDY`
4. 노트북에서 `python -m app` (시리얼 포트는 `.env`)
5. 우노 전원 → 켜진 직후는 STOP
6. 카드 1 + 리셋 버튼 → 운전 시작
7. 브라우저에서 `http://localhost:8000` 대시보드 확인
