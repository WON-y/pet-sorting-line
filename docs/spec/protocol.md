# 통신 규격 (protocol)

이 문서가 **모든 메시지의 기준**입니다. 코드가 이 문서와 다르면 코드가 틀린 것입니다.
메시지를 추가하거나 바꿀 때는 이 문서 → `common/protocol.py` → `tests/test_protocol.py` 순서로 함께 고칩니다.

## 0. 연결 한눈에 보기

```
손 1~4 (micro:bit) ──라디오── 게이트웨이 micro:bit ──USB 시리얼── 노트북 app (python -m app)
                                   │ 핀 P0·P1 모드 2비트, P2 하트비트      │ USB 시리얼 (HOLD, 선택 PAUSE·GO)
                                   └──────────── 아두이노 우노 ───────────┘
노트북 app = 웹캠 판정 + 대시보드(FastAPI) + SQLite, 한 프로그램 (기본, 도커 없음)
(선택) 노트북 app ──MQTT── mosquitto(도커) ──MQTT── dashboard(도커)
```

| 구간 | 방식 | 안전 경로? |
| --- | --- | --- |
| 손 ↔ 손 ↔ 게이트웨이 | micro:bit 라디오 (`sendValue`) | 일부(손 3 `mode`가 모드 핀·하트비트가 됨) |
| 게이트웨이 → 아두이노 | 핀 P0·P1(모드 2비트), P2(하트비트) | **예** |
| 게이트웨이 ↔ 노트북 | USB 시리얼 115200 | 아니오 |
| 노트북 ↔ 아두이노 | USB 시리얼 115200 | 아니오 (검사 멈춤·재개만) |
| 노트북 → 대시보드 | 같은 프로그램 안 (기본) 또는 MQTT (JSON, 도커) | 아니오 (기록·표시만) |

**원칙: 노트북·도커·MQTT는 정지 경로에 들어가지 않는다.** 이것들이 모두 꺼져도 벨트는 멈출 수 있어야 한다. → `safety_rules.md`

---

## 1. micro:bit 라디오

2026-11-28 변경: 실제 제어 코드(`code/microbit/*.ts`)의 **이름·값 방식**으로 통일. 예전 문자열 메시지(`M1`, `D2`, `HB3`, `J12,CO`, `ACK1,12`, `H1,DONE`)는 없앴다.

- 라디오 그룹: `config/settings.yaml`의 `radio.group` = **73**. 손 4대와 게이트웨이 코드의 `RADIO_GROUP`도 같게. 다른 팀과 겹치면 모두 함께 바꾼다.
- 모든 메시지는 `radio.sendValue(이름, 숫자)`. 모르는 이름은 무시한다.

| 이름 | 보내는 쪽 | 받는 쪽 | 값 | 뜻 |
| --- | --- | --- | --- | --- |
| `mode` | 손 3 | 전체 | 1~4 | 현재 운전 모드 (`modes_and_states.md` 1절). **0.3초마다 다시 보내 살아 있음 신호를 겸한다** |
| `help` | 손 3 | 전체 | 0 / 1 | 도움 요청 꺼짐 / 켜짐 (선택 S1). 모드와 별개 |
| `dng` | 손 3 | 전체 | 0 / 1 / 2 | 접근 위험: 정상 / 주의 거리 / 정지 거리 |
| `jdg` | 게이트웨이 | 손 1·2 | 순번 × 10 + 판정 번호 | 병 판정 (예: 순번 57, 판정 4 → 574). 20ms 간격 3번 반복, 받는 쪽은 순번이 직전과 같으면 무시 |

판정 번호 (게이트웨이·손 1·2 공통):

| 번호 | 판정 코드 | 뜻 | 분기하는 손 |
| --- | --- | --- | --- |
| 0 | `RE` | 재검사 | 손 2 |
| 1 | `OK` | 투명 적합 | 없음 (두 손 모두 날개판 나란히) |
| 2 | (없음) | 내용물 남음 — 손 2 코드에는 있지만 지금 판정 모델에는 없는 클래스. 노트북은 보내지 않는다 | 손 2 |
| 3 | `NG` | 부적합 (투명·라벨 있음) — 2단계 | 손 2 |
| 4 | `CO` | 유색·불투명 (라벨 무관) — 1단계 | 손 1 |

- 손 1·2는 `jdg`를 받으면 자기 담당이면 날개판을 비스듬히, 아니면 나란히 돌리고 **다음 판정까지 그 각도를 유지**한다. 그래서 `OK`도 반드시 보낸다.
- 손은 응답(ACK·상태)을 보내지 않는다.
- `mode`가 끊기면: 손 1·2·4는 2초 뒤 그 자리 멈춤·`?` 표시, 게이트웨이는 1.5초 뒤 모드 핀 `00` + 하트비트 멈춤.

## 2. 게이트웨이 micro:bit ↔ 노트북 (USB 시리얼)

- 115200 baud, 한 줄 = 한 메시지, 줄 끝 `\n`. 파이썬 기준: `common/protocol.py`의 `encode_judgment`, `parse_gateway_line`.
- 노트북 → 게이트웨이: `J<판정 번호>` (`J0`~`J4`). 예: `NG` → `J3\n`
- 게이트웨이 → 노트북:

| 줄 | 뜻 |
| --- | --- |
| `ACK,<순번>,<판정 번호>` | 판정을 라디오로 보냈음 (손이 받았다는 뜻은 아님) |
| `MODE,<n>` | 손 3 모드가 n(1~4)으로 바뀜 |
| `HELP,0` / `HELP,1` | 도움 요청 꺼짐 / 켜짐 |
| `DNG,0` / `DNG,1` / `DNG,2` | 접근 위험 단계가 바뀜 |
| `LINK,OK` / `LINK,LOST` | 손 3 신호를 받기 시작함 / 끊김 (끊기면 게이트웨이가 모드 핀 `00`) |
| `ERR,<받은 내용>` | 형식이 틀린 줄 |

- 노트북은 게이트웨이 포트(`GATEWAY_PORT`)가 있으면 항상 연결해 모드·위험·도움 요청을 기록한다. 판정을 보내는 것은 `app.sorting: true`일 때만.

## 3. 게이트웨이 → 아두이노 핀 (안전 경로)

2026-11-26 변경: 실제 제어 코드(`code/microbit/gateway_bridge.ts`)의 모드 2비트 방식으로 통일. 우노 펌웨어는 `safety/belt_controller` 통합본.

| 핀 (micro:bit → 우노) | 이름 | 규칙 |
| --- | --- | --- |
| P0 → D6 | MODE_B0 | 모드 비트 0 |
| P1 → D7 | MODE_B1 | 모드 비트 1. (P1,P0) = 자동 `01`, 저속 `10`, 일시 정지 `00`, 점검 잠금 `11`. 우노는 `INPUT_PULLUP`이라 **선이 빠지면 `11` = 정지** (고장 시 안전 쪽) |
| P2 → D8 | HEARTBEAT | 게이트웨이가 손 3 신호를 받는 동안 0.1초마다 HIGH/LOW를 바꿈. 우노는 `safety.heartbeat_timeout_ms`(600ms) 동안 변화가 없으면 정지 |
| GND ↔ GND | | 반드시 연결 |

- micro:bit에 5V를 직접 넣지 않는다 (우노 → micro:bit 방향 선은 없다).
- 손 3이 정지 거리 안의 사람을 감지하면 모드를 정지(3)로 바꾸고, 게이트웨이는 핀을 `00`으로 내린다. 노트북은 거치지 않는다.
- 우노는 모드 `00`·`11`이 되면 **잠긴다**. 모드가 `01`·`10`으로 돌아와도 리셋 버튼을 눌러야만 다시 돈다.
- 파이썬 기준 값: `common/protocol.py`의 `UNO_PIN_MODES`, `UNO_RUN_MODES`.

## 4. 노트북 ↔ 아두이노 (USB 시리얼, 안전 경로 아님)

- 115200 baud, 한 줄 = 한 메시지.
- 노트북 → 우노

| 명령 | 뜻 |
| --- | --- |
| `PAUSE` | (`app.stop_to_judge: true`일 때만) 웹캠이 병 도착을 감지함 → 검사 자리에서 멈춤 (검사 멈춤, 잠기지 않음). 기본 방식에서는 보내지 않는다 |
| `GO` | 판정 끝 → 검사 멈춤(`PAUSE`, IR 도착 센서)을 풀고 다시 돌림. 잠김 상태에서는 무시 |
| `HOLD` | 정지 + 잠김. 다시 돌리려면 리셋 버튼 |
| `PING` | 연결 확인 |

- 속도는 모드 핀으로만 정한다 (예전 `SPD`, `ARM` 명령은 없앴다). **재가동 명령은 없다.**
- 사람이 시리얼 모니터에서 쓰는 조정 명령(`?`, `N800`, `S300`, `A1500`, `D`, `T`, 시험 모드 `1`~`4`)은 `safety/belt_controller.ino` 머리말 참고.

- 우노 → 노트북

| 메시지 | 뜻 |
| --- | --- |
| `EVT,PAUSE` | `PAUSE`를 받아 검사 멈춤 |
| `EVT,ARRIVE` | (선택) IR 도착 센서가 병 감지, 스스로 검사 멈춤. 웹캠 감지의 보조 |
| `EVT,STOP,<cause>` | 정지·잠김. cause: `POWERON`(전원 켬), `HB`(하트비트 끊김), `MODE`(모드 핀 00·11), `ESTOP`(비상정지 감지), `HOLD`(명령), `IR`(IR 커튼, 선택) |
| `EVT,RUN` | 리셋 버튼으로 재가동 완료 |
| `STATE,<run>,<speed>` | 주기 상태(1초). run: `RUN`/`STOP`/`PAUSE`, speed: `N`/`S` |
| `PONG` | |

비상정지 버튼은 12V 전원을 직접 끊으므로 우노가 알 수 없을 수 있다. 우노는 TB6600 전원 감시가 없으면 `EVT,STOP,HB`나 사용자 기록으로 대신한다.

## 5. MQTT (노트북 app → 대시보드)

- 기본(`app.record: local`)은 MQTT를 쓰지 않고 같은 프로그램 안에서 대시보드 `handle_message(토픽, payload)`로 바로 넘긴다. 토픽 이름과 payload는 아래와 같다.
- 도커로 대시보드를 따로 띄울 때만(`app.record: mqtt`) 브로커 `mqtt:1883` (도커 안), 노트북에서는 `localhost:1883`.
- 모든 payload는 JSON, UTF-8. 공통 필드 `ts`(ISO 8601, 초까지, KST), `src`(보낸 프로그램).
- QoS 1, retain은 `pet/state`만 true.

| 토픽 | 언제 | payload 예 |
| --- | --- | --- |
| `pet/judgment` | 병 판정 확정 | `{"ts":"2026-11-20T14:03:05+09:00","src":"app","id":12,"cls":"clear_label","code":"NG","conf":0.93,"frames":1,"trigger":"CAM","img":"20261120/W_20261120-140305_012_crop.jpg","full":"20261120/W_20261120-140305_012_full.jpg"}` (trigger: `CAM` 웹캠 / `IR` 도착 센서 / `MANUAL` 대시보드, img·full: 사진 폴더 기준 경로, detail: 두 모델 각각의 결과 `{"color":"clear","color_conf":0.98,"label":"label","label_conf":0.93}`, 4클래스 모델 하나일 때는 없음) |
| `pet/sort` | 판정을 손에 보냄 (`app.sorting: true`) 또는 병 처리 중단 | `{"ts":...,"id":12,"hand":2,"result":"SENT","seq":57,"late":false}` (result: `SENT` 게이트웨이가 라디오로 보냄, `ABORTED` 정지·잠금으로 중단. hand: 분기하는 손, `OK`면 null. late: 벨트를 멈추지 않을 때 보낼 시각을 넘김 → 이 병은 잘못 갔을 수 있음) |
| `pet/mode` | 운전 모드 변경 | `{"ts":...,"mode":2,"by":"hand3"}` (mode 1~4, by: `hand3` 손 3 수신호·카드 (게이트웨이 `MODE,n`) / `gesture` 노트북 손짓, 예정) |
| `pet/safety` | 경고·정지·재가동 | `{"ts":...,"level":2,"event":"STOP","cause":"IR"}` (event: `WARN` 접근 경고, `STOP` 정지, `RUN` 재가동, `CLEAR` 경고 해제, `HELP`·`HELP_END` 도움 요청 켜짐·꺼짐, `ERROR` 오류. ERROR cause: `NO_ACK` 게이트웨이 응답 없음, `LINK_LOST` 손 3 신호 끊김, `TOO_CLOSE` 병 간격이 좁아 뒷 병 판정을 제때 보낼 수 없음) |
| `pet/hand/<n>` | (예비) 손 상태 | 지금 손은 상태를 보내지 않아 쓰지 않는다 |
| `pet/state` | 1초마다 | `{"ts":...,"run":"RUN","speed":"N","mode":1,"danger":0,"state":"AUTO","line":"IDLE","bottle":12,"cause":null,"help":0,"link":true}` (state 우선순위: `modes_and_states.md` 3절, link: 손 3 신호를 받는 중인지, 게이트웨이가 없으면 null) |

## 6. 대시보드 HTTP API

| 메서드 | 경로 | 응답 |
| --- | --- | --- |
| GET | `/health` | `{"ok":true}` |
| GET | `/api/summary` | 통별 개수, 재검사 수, 정지 횟수, 아차사고 수 |
| GET | `/api/events?type=&limit=` | 최근 이벤트 목록 |
| GET | `/api/captures?limit=&unlabeled=` | 촬영 사진 목록 (재학습용) |
| POST | `/api/captures/{id}/label` | `{"label": "clear_label"}` 사람이 확인한 정답. 4클래스, `exclude`(학습에서 뺌), `""`(미확인) |
| GET | `/api/captures.csv` | 정답 단 사진 목록 (`training/manifest.csv`와 같은 열, source=belt) |
| GET | `/captures/<경로>` | 사진 파일 (사진 폴더 밖은 못 읽음) |
| GET | `/api/line` | 라인 상태 (벨트, 진행 상태, 감지 상태, 최근 판정). 라인 없이 띄우면 503 |
| GET | `/api/line/frame.jpg` | 실시간 화면 (판정 구역·박스 표시) |
| POST | `/api/line/baseline` | 빈 벨트 기준 사진 저장 |
| POST | `/api/line/roi` | `{"roi": [x1,y1,x2,y2]}` 또는 `{"roi": null}` 판정 구역 (실행 중에만, 계속 쓰려면 settings.yaml) |
| POST | `/api/line/capture` | 지금 촬영·판정 |
| POST | `/api/line/hold` | 우노에 `HOLD` |
| POST | `/api/line/reset` | **가상 벨트만**: 리셋 버튼 흉내. 실제 우노면 403 |
| POST | `/api/line/mode` | **가상 벨트만**: `{"mode": 1~4}` 손 3 모드 흉내. 실제 우노면 403 |
| GET | `/api/phone` | 휴대폰 카메라 상태 `{"enabled":true,"urls":[...],"connected":true,"frames":12,"age_ms":80}`. `--phone`이 아니면 `{"enabled":false}` |
| GET | `/api/phone/qr.svg?i=` | 휴대폰 접속 주소(토큰 포함) QR. `--phone`이 아니면 404 |
| GET | `/` | 대시보드 화면 (정적 HTML) |

휴대폰 카메라 서버 (`python -m app --phone`, `https://<노트북IP>:<phone.port>`, 자체 서명 인증서, 같은 와이파이에만):

| 메서드 | 경로 | 응답 |
| --- | --- | --- |
| GET | `/phone?k=<토큰>` | 휴대폰 카메라 페이지 (카메라 → JPEG 전송) |
| GET | `/phone/config?k=<토큰>` | `{"send_width":1280,"jpeg_quality":0.85,"interval_ms":100}` |
| POST | `/phone/frame?k=<토큰>` | 본문 = JPEG 한 장 (`image/jpeg`, 5MB 이하). `{"ok":true,"seq":12}`. 토큰이 틀리면 403 |

토큰은 실행할 때마다 새로 만들고 대시보드 QR에만 나온다. 이 서버에는 시험 버튼이 없다.
