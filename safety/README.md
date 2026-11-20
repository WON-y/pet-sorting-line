# 안전·벨트 제어 (아두이노 우노)

**이 폴더를 고치기 전에 `docs/spec/safety_rules.md`를 반드시 읽는다.**

- 실행 위치: 아두이노 우노. 언어: Arduino C++. 보드: `arduino:avr:uno`
- 담당: R2(위험 정지), R3(비상정지·리셋), 벨트 구동(TB6600), IR 도착·IR 커튼
- 노트북 없이도 정지가 동작해야 한다.

## 핀 배치 (초안 — 배선 후 `docs/hardware/wiring.md`와 함께 확정)

| 우노 핀 | 연결 | 방향 | 비고 |
| --- | --- | --- | --- |
| D2 | 게이트웨이 P0 DANGER | 입력 PULLUP | HIGH 또는 끊김 = 정지 |
| D3 | 게이트웨이 P1 HEARTBEAT | 입력 PULLUP | 1초 변화 없으면 정지 |
| D4 | 게이트웨이 P2 STATE | 출력 | 1kΩ·2kΩ 분압 후 micro:bit로 |
| D5 | IR 도착 센서 | 입력 | LOW = 병 감지 (모듈에 따라 확인) |
| D6 | IR 커튼 센서 (여러 개면 직렬 또는 OR) | 입력 | LOW = 손 감지 → 정지 |
| D7 | 리셋 버튼(택트 스위치 모듈) | 입력 PULLUP | ARM 후 5초 안에만 유효 |
| D8 | TB6600 ENA | 출력 | 정지 시 비활성 |
| D9 | TB6600 PUL | 출력 | 스텝 펄스 |
| D10 | TB6600 DIR | 출력 | |
| D11 | 전원 릴레이 IN | 출력 | RUN일 때만 붙임 |

## 파일

- `belt_controller/belt_controller.ino` — 펌웨어 (CI에서 컴파일 검사)

## 고친 뒤 반드시

1. 정지 시험 N1~N5를 다시 하고 `docs/tests/kpi_log.md`에 기록
2. PR의 안전 체크리스트 작성
