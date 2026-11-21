# 설정 규격

## 원칙

- 실험 중 바꾸는 숫자(거리, 기준값, 좌표, 포트)는 코드에 직접 쓰지 않고 `config/settings.yaml`에 둔다.
- 컴퓨터마다 다른 값(시리얼 포트 이름, 비밀 값)은 `.env`에 둔다. `.env`는 깃허브에 올리지 않고 `.env.example`만 올린다.
- 파이썬은 `common/config.py`의 `load_settings()`로 읽는다. 환경 변수가 있으면 yaml 값보다 우선한다.
- micro:bit·아두이노 펌웨어는 yaml을 읽지 못한다. **같은 값을 펌웨어 상단 상수로 적고**, 바꿀 때 양쪽을 함께 고친다. 상수 옆에 `// settings.yaml: safety.warn_distance_cm` 처럼 출처를 주석으로 단다.

## 키 목록

| 키 | 기본값 | 쓰는 곳 | 설명 |
| --- | --- | --- | --- |
| `radio.group` | 37 | 모든 micro:bit | 라디오 그룹 |
| `serial.gateway_port` | "" | app | 게이트웨이 시리얼 포트 (`GATEWAY_PORT`) |
| `serial.arduino_port` | "" | app | 우노 시리얼 포트 (`ARDUINO_PORT`) |
| `serial.baud` | 115200 | app, 펌웨어 | |
| `mqtt.host` / `mqtt.port` | localhost / 1883 | app | 도커 안에서는 `MQTT_HOST=mqtt` |
| `vision.camera_index` | 1 | vision/bottle, vision/webtest | 판정용 USB 웹캠 번호 (노트북마다 다를 수 있음) |
| `vision.weights` | training/weights/best.pt | vision/bottle | |
| `vision.roi` | null | vision/bottle, training | 판정 구역 [x1,y1,x2,y2] |
| `vision.letterbox_color` | [114,114,114] | vision/bottle, training | 학습 전처리와 같아야 함 |
| `vision.frames` | 1 | vision/bottle | 판정 프레임 수 (벨트 정지 후 1프레임) |
| `vision.conf_threshold` | 0.6 | vision/bottle | 재검사 기준 |
| `webtest.port` | 8100 | vision/webtest | 카메라 인식 웹 테스트 포트 |
| `webtest.interval_ms` | 500 | vision/webtest | 자동 인식 간격 |
| `webtest.fallback_model` | yolo11n-cls.pt | vision/webtest | 학습 가중치가 없을 때 쓰는 기본 분류 모델 |
| `gesture.*` | | vision/gesture | 손짓 인식 |
| `safety.warn_distance_cm` | 40 | 손 3 | 접근 경고 거리 |
| `safety.stop_distance_cm` | 20 | 손 3 | 위험 정지 거리 |
| `safety.heartbeat_period_ms` | 200 | 손 3 | |
| `safety.heartbeat_timeout_ms` | 1000 | 우노 | |
| `safety.arm_valid_ms` | 5000 | 우노 | 리셋 버튼 유효 시간 |
| `app.ack_timeout_ms` | 1500 | app | 손 ACK 대기 |
| `app.sort_hold_ms` | 1200 | 손 1·2 | 날개판 유지 시간 |

## 환경 변수 (.env)

| 변수 | 예 | 설명 |
| --- | --- | --- |
| `GATEWAY_PORT` | COM5 | 게이트웨이 micro:bit 포트 |
| `ARDUINO_PORT` | COM6 | 우노 포트 |
| `MQTT_HOST` | localhost | |
| `MQTT_PORT` | 1883 | |
| `DB_PATH` | /data/pet.db | 대시보드 DB 위치 (컨테이너 안) |
