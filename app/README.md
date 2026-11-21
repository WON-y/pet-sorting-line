# 통합 실행 (노트북)

- 실행: `python -m app` (실제 하드웨어) / `python -m app --mock` (하드웨어 없이)
- 도커: 모의 실행만 `simulator` 컨테이너로 (`CONTAINER.md`)
- **정지 경로에 끼지 않는다.** 이 프로그램이 죽어도 우노가 멈춘다.

## 구조

| 파일 | 내용 |
| --- | --- |
| `controller.py` | `LineController` — 상태 머신 (`docs/spec/modes_and_states.md` 3·5절). 입력을 받아 할 일(Action) 목록을 돌려주는 순수 로직, pytest로 시험 |
| `main.py` | 시리얼·웹캠·MQTT를 연결하고 루프를 돌림 |
| `mock.py` | 가짜 게이트웨이·우노·판정 |

## 병 한 개의 흐름

`EVT,ARRIVE` → capture → 1프레임 판정 → `pet/judgment` 발행 → (OK면 바로 `GO`) / (CO·NG·RE면 `TX:J<id>,<code>` → ACK → DONE → `GO`)

## 할 일

- [ ] 손짓(gesture) 카메라를 루프에 연결 → 확정 시 `on_radio(MODE, by="gesture")` + `TX:M<n>`
- [ ] 우노 `STATE` 주기 메시지 반영
- [ ] 실제 하드웨어로 ACK 시간 초과 값 조정
