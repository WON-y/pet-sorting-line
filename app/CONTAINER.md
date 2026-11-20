# 컨테이너: simulator (app 모의 실행)

## 역할

- `python -m app --mock`을 도커 안에서 돌려, **하드웨어 없이** 가짜 병 도착·판정·손 응답·접근 경고·위험 정지 이벤트를 MQTT로 발행한다.
- 대시보드 화면 개발, 발표 리허설, 팀원 온보딩에 쓴다.
- 실제 하드웨어 실행은 이 컨테이너가 아니라 **노트북에서 직접** `python -m app`으로 한다. 웹캠과 USB 시리얼(micro:bit, 우노)은 윈도우·맥 도커에서 연결이 어렵기 때문이다.

## 도커 정보

| 항목 | 값 |
| --- | --- |
| 이미지 | `app/Dockerfile` (python:3.12-slim + requirements.txt) |
| 프로필 | `mock` → 평소 `docker compose up`에는 켜지지 않음 |
| 포트 | 없음 |
| 환경 변수 | `MQTT_HOST`(mqtt), `MQTT_PORT`(1883) |
| 의존 | `mqtt`, `dashboard` |

## 실행

```bash
docker compose --profile mock up         # mqtt + dashboard + simulator
# 도커 없이 노트북에서 모의 실행
python -m app --mock --duration 60
```

## 가짜 이벤트 규칙 (`app/mock.py`)

- 3초마다 병 도착, 병마다 무작위 클래스, 약 7%는 낮은 신뢰도 → 재검사
- 판정을 보내면 0.2초 뒤 ACK, 1.4초 뒤 DONE
- 가끔(평균 약 40초마다) 접근 경고 3초, 드물게(평균 약 3분마다) IR 위험 정지 후 4초 뒤 재가동

## 작업 규칙

- 모의 이벤트도 실제와 같은 규격(`common/protocol.py`)으로 만든다. 모의에서만 쓰는 메시지를 만들지 않는다.
