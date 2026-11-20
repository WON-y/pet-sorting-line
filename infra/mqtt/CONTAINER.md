# 컨테이너: mqtt

## 역할

- 노트북 app(발행)과 dashboard(구독) 사이에서 메시지를 전달하는 MQTT 브로커(eclipse-mosquitto 2).
- 기록·표시용 이벤트만 지나간다. **안전 정지 신호는 이 브로커를 거치지 않는다** (`docs/spec/safety_rules.md`).

## 도커 정보

| 항목 | 값 |
| --- | --- |
| 이미지 | `eclipse-mosquitto:2` (공식 이미지, 따로 빌드 안 함) |
| 포트 | 1883 (노트북 app은 `localhost:1883`, 컨테이너끼리는 `mqtt:1883`) |
| 설정 | `infra/mqtt/mosquitto.conf` (읽기 전용으로 연결) |
| 보안 | 익명 접속 허용. 시연용 로컬 네트워크 전용이므로 외부에 포트를 열지 않는다 |

## 토픽

규격: `docs/spec/protocol.md` 5절. 접두사 `pet/` (`config/settings.yaml`의 `mqtt.topic_prefix`).

## 확인 방법

```bash
docker compose up -d mqtt
# 모든 메시지 보기
docker exec -it pet-mqtt mosquitto_sub -t 'pet/#' -v
# 시험 메시지 보내기
docker exec -it pet-mqtt mosquitto_pub -t pet/mode -m '{"ts":"2026-11-20T10:00:00+09:00","src":"cli","mode":2,"by":"card"}'
```

## 작업 규칙

- 설정을 바꾸면 이 문서의 표도 같이 고친다.
- 인증을 추가하려면 app·dashboard 환경 변수와 `docs/spec/config.md`를 함께 바꾼다.
