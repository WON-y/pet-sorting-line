# 안전·벨트 제어 (아두이노 우노)

**이 폴더를 고치기 전에 `docs/spec/safety_rules.md`를 반드시 읽는다.**

- 실행 위치: 아두이노 우노. 언어: Arduino C++. 보드: `arduino:avr:uno`
- 담당: R2(위험 정지), R3(비상정지·리셋), 벨트 구동(TB6600), 검사 멈춤(PAUSE/GO), (선택) IR 도착 센서
- 노트북 없이도 정지가 동작해야 한다.
- `belt_controller.ino`는 `code/arduino/conveyor/conveyor.ino`의 구동 부분(모드 2비트 핀, 가감속, 시리얼 조정)을 바탕으로 안전 기능(잠김, 릴레이·ENA 이중 차단, HOLD, 원인 기록)을 합친 **통합본**이다 (2026-11-26). 앞으로 벨트 펌웨어는 이 파일만 고친다.

## 핀 배치 (게이트웨이 `code/microbit/gateway_bridge.ts` 배선과 같음)

| 우노 핀 | 연결 | 방향 | 비고 |
| --- | --- | --- | --- |
| D2 | (선택) IR 도착 센서 | 입력 PULLUP | LOW = 병 감지 → 검사 멈춤 + `EVT,ARRIVE`. `USE_IR_ARRIVE` |
| D3 | TB6600 PUL+ | 출력 | 스텝 펄스 |
| D4 | TB6600 DIR+ | 출력 | |
| D5 | TB6600 ENA+ | 출력 | 잠김이면 드라이버 끔 |
| D6 | 게이트웨이 P0 (모드 비트 0) | 입력 PULLUP | |
| D7 | 게이트웨이 P1 (모드 비트 1) | 입력 PULLUP | (P1,P0) 자동 01, 저속 10, 정지 00, 점검 잠금 11. 선이 빠지면 11 = 정지 |
| D8 | 게이트웨이 P2 (하트비트) | 입력 PULLUP | 0.6초 변화 없으면 정지 |
| D9 | (선택) IR 커튼 | 입력 PULLUP | LOW = 손 감지 → 정지. `USE_IR_CURTAIN` (지금은 안 씀) |
| D10 | 리셋 버튼 | 입력 PULLUP | 누르면 LOW. 재가동은 이 버튼으로만 |
| D11 | (선택) 비상정지 보조 접점 | 입력 PULLUP | 눌림 = HIGH. `USE_ESTOP_SENSE` |
| D12 | 전원 릴레이 IN | 출력 | 잠김이 아닐 때만 붙임 |
| PUL-/DIR-/ENA-, micro:bit GND | GND | | 반드시 공통 |

## 동작 요약

| 상태 | 언제 | 벨트 | 풀리는 방법 |
| --- | --- | --- | --- |
| STOP (잠김) | 전원 켬, 하트비트 끊김, 모드 핀 00·11, 비상정지 감지, `HOLD`, (선택) IR 커튼 | 즉시 멈춤, ENA 끔, 릴레이 개방 | 모드 핀 01·10 + 하트비트 정상 + **리셋 버튼** |
| PAUSE (검사 멈춤) | 노트북 `PAUSE`, (선택) IR 도착 센서 | 즉시 멈춤, 토크 유지 | 노트북 `GO` |
| RUN | 잠김·멈춤 아님 | 모드대로 보통·저속 (가감속) | |

## 파일

- `belt_controller/belt_controller.ino` — 펌웨어 (CI에서 컴파일 검사)

## 고친 뒤 반드시

1. 정지 시험 N1~N5를 다시 하고 `docs/tests/kpi_log.md`에 기록
2. PR의 안전 체크리스트 작성
