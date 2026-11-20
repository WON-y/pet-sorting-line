# 개발 규칙

## 1. 문서가 먼저

- 규격(`docs/spec/`)이 코드보다 우선이다. 규격을 바꾸는 일은 코드보다 먼저, 같은 PR 안에서 한다.
- 요구사항 ID를 어디서나 쓴다: 필수 `R1~R8`, 선택 `S1~S11`, KPI `N1~N15` (정의는 `docs/PRD.md`).
- 각 모듈 폴더의 `README.md`가 그 모듈의 설명서다. 기능을 바꾸면 README도 고친다.

## 2. 언어와 이름

| 대상 | 규칙 | 예 |
| --- | --- | --- |
| 문서, 주석, 커밋 설명 | 한국어 | |
| 파이썬 파일·함수·변수 | 영어 snake_case | `classify_frame`, `conf_threshold` |
| 파이썬 클래스 | PascalCase | `BottleClassifier` |
| 상수 | UPPER_SNAKE | `HEARTBEAT_TIMEOUT_MS` |
| 아두이노 | camelCase 함수, UPPER_SNAKE 상수 | `stopBelt()`, `PIN_DANGER` |
| 파일·폴더 이름 | 영어 소문자, `_` 연결, 한글·공백 금지 | `belt_controller.ino` |
| 이미지 파일 | `출처_병번호_순번.jpg` | `W_B12_004.jpg` |

## 3. 파이썬

- 파이썬 3.11 이상. 공통 패키지는 `requirements.txt`, 대시보드는 `dashboard/requirements.txt`.
- 스타일 검사: `ruff check .` (CI에서 자동).
- 시험: `pytest` (CI에서 자동). 하드웨어 없이 돌아가야 한다. 하드웨어가 필요한 부분은 모의(mock) 객체로 바꿔 시험한다.
- 무거운 라이브러리(ultralytics, mediapipe, cv2)는 함수 안에서 import해 CI와 시험이 가볍게 돌게 한다.
- 메시지 문자열을 코드에 직접 쓰지 말고 `common/protocol.py`의 함수(`encode_*`, `parse_*`)를 쓴다.
- 설정 숫자는 `common/config.py`로 읽는다.

## 4. micro:bit (MakeCode)

- 손마다 폴더 하나: `hardware/hand1_sorter` 등. 안에 `.hex`와 함께 **MakeCode 공유 링크** 또는 프로젝트 파일(`main.ts`, `pxt.json`)을 남긴다. `.hex`만 있으면 다시 고칠 수 없다.
- 프로그램 맨 위에 설정 상수 블록(라디오 그룹, 거리 등)을 모은다.
- 받은 메시지는 LED에 잠깐 표시하고, 모르는 메시지는 무시한다.
- 상태(대기·분기·복귀, 모드별)를 변수 하나로 관리한다.

## 5. 아두이노

- `safety/belt_controller/belt_controller.ino` 하나. Arduino IDE 또는 arduino-cli, 보드 `arduino:avr:uno`.
- CI에서 컴파일 검사를 한다. 컴파일이 안 되는 코드는 합치지 않는다.
- `safety_rules.md` 4절을 지킨다.

## 6. Git

- 브랜치: `main`은 항상 시연 가능한 상태. 작업은 `feat/R4-bottle-judge`, `fix/N2-stop-delay`처럼 ID를 넣은 브랜치에서.
- 커밋 메시지: `[R4] 레터박스 전처리 추가`처럼 맨 앞에 ID.
- PR로 합친다. CI 통과 + 팀원 1명 확인. `safety/`를 바꾸는 PR은 안전 체크리스트 필수.
- 올리지 않는 것: 학습 이미지, 영상, `data/logs`, `runs/`, `.env`, 개인정보 문서. (`.gitignore` 참고)

## 7. AI 도구(Claude 등)로 작업할 때

- 시작 전에 루트 `CLAUDE.md`와 작업할 폴더의 `README.md`를 읽게 한다.
- 규격과 다른 코드를 만들면 규격을 고칠지 코드를 고칠지 사람에게 먼저 묻는다.
- 안전 영역은 사람이 실제 시험하기 전까지 "완료"로 보지 않는다.
