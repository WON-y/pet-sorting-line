# 하드웨어 제어 (AIHand 손 1~4)

AIHand마다 micro:bit 하나가 들어 있고, MakeCode로 만든 프로그램이 손가락·손목 서보와 센서를 움직인다.

**프로그램은 `code/microbit/`에 있다 (제어 담당 코드가 기준).** 이 폴더에는 손별 설명과 시험 체크리스트만 둔다.
코드가 무엇을 하는지 자세한 설명은 `code/README.md`, 왜 그렇게 했는지는 `code/CLAUDE.md`.

| 폴더 | 손 | 프로그램 | 역할 | 담당 요구사항 |
| --- | --- | --- | --- | --- |
| `hand1_sorter` | 손 1 (작업 손) | `code/microbit/hand12_sorter.ts` (`HAND_ID = 1`) | 날개판으로 유색·불투명(`CO`) 병 분기 | R5 |
| `hand2_sorter` | 손 2 (작업 손) | `code/microbit/hand12_sorter.ts` (`HAND_ID = 2`) | 날개판으로 부적합(`NG`)·재검사(`RE`) 병 분기 | R5 |
| `hand3_signal` | 손 3 (지시대 신호 손) | `code/microbit/hand3_signal.ts` | 수신호(카드로 전환 가능) → 모드, 복창, 초음파 접근 감지. **모드의 기준** | R1, R2, R6 |
| `hand4_remote` | 손 4 (원격 신호 손) | `code/microbit/hand4_display.ts` | 떨어진 자리에서 모드·위험·도움 요청 표시 | R6, R7, S1 |

## 공통 규칙

- 실행 위치: 각 손의 micro:bit. 언어: MakeCode (JavaScript 탭에 붙여 넣기).
- 라디오 메시지는 `docs/spec/protocol.md` 1절 (`mode`, `dng`, `help`, `jdg` 이름·값 방식), 모드·우선순위는 `docs/spec/modes_and_states.md`.
- 라디오 그룹은 4대 + 게이트웨이 모두 `73`.
- 서보를 쓰는 micro:bit는 USB 시리얼을 쓸 수 없다. 디버깅은 LED·소리로 한다.
- 대여품: 펌웨어 교체·분해 금지. 날개판은 손목에 고정 장치로 붙임(원상복구 가능).
