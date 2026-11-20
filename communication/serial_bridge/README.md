# 노트북 시리얼·MQTT 연결

- 실행 위치: 노트북 (Python). `app`이 불러서 쓴다.

| 파일 | 내용 |
| --- | --- |
| `links.py` | `SerialLink`(pyserial, 실제), `FakeLink`(모의·시험) — 같은 메서드 `send`, `read_lines` |
| `mqtt_pub.py` | `MqttPublisher` — 브로커가 없으면 경고만 하고 계속 (기록용이라 라인을 멈추지 않음) |

## 포트 찾기

- 윈도우: 장치 관리자 → 포트(COM & LPT). 맥: `ls /dev/cu.usbmodem*`. 리눅스: `ls /dev/ttyACM*`
- `.env`의 `GATEWAY_PORT`, `ARDUINO_PORT`에 적는다.
