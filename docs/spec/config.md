# 설정 규격

## 원칙

- 실험 중 바꾸는 숫자(거리, 기준값, 좌표, 포트)는 코드에 직접 쓰지 않고 `config/settings.yaml`에 둔다.
- 컴퓨터마다 다른 값(시리얼 포트 이름, 비밀 값)은 `.env`에 둔다. `.env`는 깃허브에 올리지 않고 `.env.example`만 올린다.
- 파이썬은 `common/config.py`의 `load_settings()`로 읽는다. 환경 변수가 있으면 yaml 값보다 우선한다.
- micro:bit·아두이노 펌웨어는 yaml을 읽지 못한다. **같은 값을 펌웨어 상단 상수로 적고**, 바꿀 때 양쪽을 함께 고친다. 상수 옆에 `// settings.yaml: safety.warn_distance_cm` 처럼 출처를 주석으로 단다.

## 키 목록

| 키 | 기본값 | 쓰는 곳 | 설명 |
| --- | --- | --- | --- |
| `radio.group` | 73 | 모든 micro:bit | 라디오 그룹. micro:bit 코드의 `RADIO_GROUP`과 같게 |
| `serial.gateway_port` | "" | app | 게이트웨이 시리얼 포트 (`GATEWAY_PORT`) |
| `serial.arduino_port` | "" | app | 우노 시리얼 포트 (`ARDUINO_PORT`) |
| `serial.baud` | 115200 | app, 펌웨어 | |
| `mqtt.host` / `mqtt.port` | localhost / 1883 | app | 도커 안에서는 `MQTT_HOST=mqtt` |
| `vision.camera_index` | 1 | vision/bottle, vision/webtest | 판정용 USB 웹캠 번호 (노트북마다 다를 수 있음) |
| `vision.model_mode` | split | vision/bottle | `split` 색 모델 + 라벨 모델 / `single` 4클래스 모델 하나 |
| `vision.color_model.weights` | training/weights/color_best.pt | vision/bottle | 색 모델 (clear/color) |
| `vision.color_model.names` | {} | vision/bottle | 모델 클래스 이름 → clear·color (이름이 다를 때만) |
| `vision.label_model.weights` | training/weights/label_best.pt | vision/bottle | 라벨 모델 (label/nolabel) |
| `vision.label_model.names` | {} | vision/bottle | 모델 클래스 이름 → label·nolabel (이름이 다를 때만) |
| `vision.weights` | training/weights/best.pt | vision/bottle, webtest | 예전 4클래스 모델 (`single`일 때, 웹 테스트) |
| `vision.roi` | null | vision/bottle, training | 판정 구역 [x1,y1,x2,y2] |
| `vision.letterbox_color` | [114,114,114] | vision/bottle, training | 학습 전처리와 같아야 함 |
| `vision.frames` | 1 | vision/bottle | 판정 프레임 수 (벨트 정지 후 1프레임) |
| `vision.conf_threshold` | 0.6 | vision/bottle | 재검사 기준 |
| `vision.camera_size` | [1920, 1080] | vision/bottle | 웹캠 해상도 요청 |
| `vision.video_file` | "" | app | 웹캠 대신 녹화 영상 (`--video`와 같음) |
| `vision.crop_mode` | box | vision/bottle | `box` 병 둘레 / `roi` 판정 구역 전체 |
| `vision.crop_margin` | 0.20 | vision/bottle | box 자르기 여백 |
| `vision.capture_dir` | data/captures | app | 판정 사진 저장 폴더 (재학습용) |
| `vision.detect.diff_thresh` | 40 | vision/bottle/detect | 기준 사진과 밝기 차이 기준 |
| `vision.detect.min_area_frac` | 0.03 | vision/bottle/detect | 물체로 볼 최소 크기 (구역 대비) |
| `vision.detect.edge_margin` | 10 | vision/bottle/detect | 가장자리에서 떨어져야 하는 픽셀 |
| `vision.detect.stable_frames` | 5 | vision/bottle/detect | 완전히 들어온 상태가 이만큼 이어지면 멈춤 |
| `vision.detect.clear_frames` | 10 | vision/bottle/detect | 구역이 이만큼 비어야 다음 병 |
| `phone.port` | 8443 | app (`--phone`) | 휴대폰 카메라 https 포트 (0.0.0.0, 같은 와이파이) |
| `phone.host_ip` | "" | app | QR에 넣을 노트북 주소. 비우면 자동 |
| `phone.send_width` | 1280 | 휴대폰 페이지 | 휴대폰이 보내는 사진 폭 |
| `phone.jpeg_quality` | 0.85 | 휴대폰 페이지 | JPEG 화질 (0~1) |
| `phone.interval_ms` | 100 | 휴대폰 페이지 | 한 장 보낸 뒤 다음 장까지 쉬는 시간 |
| `phone.timeout_ms` | 2000 | vision/bottle/phone.py | 사진이 이 시간 안 오면 끊김 (도착·비었음 신호 안 냄) |
| `webtest.port` | 8100 | vision/webtest | 카메라 인식 웹 테스트 포트 |
| `webtest.interval_ms` | 500 | vision/webtest | 자동 인식 간격 |
| `webtest.fallback_model` | yolo11n-cls.pt | vision/webtest | 학습 가중치가 없을 때 쓰는 기본 분류 모델 |
| `gesture.*` | | vision/gesture | 손짓 인식 |
| `safety.warn_distance_cm` | 40 | 손 3 | 접근 경고 거리 |
| `safety.stop_distance_cm` | 20 | 손 3 | 위험 정지 거리 |
| `safety.heartbeat_period_ms` | 200 | 손 3 | |
| `safety.heartbeat_timeout_ms` | 600 | 우노 | 게이트웨이가 0.1초마다 토글 |
| `app.record` | local | app | `local` SQLite 바로 기록 / `mqtt` 도커 대시보드로 발행 (`RECORD`) |
| `app.sorting` | false | app | 판정을 손 1·2에 보내 분기할지 |
| `app.settle_ms` | 400 | app | 벨트 멈춘 뒤 촬영까지 대기 |
| `app.resume_delay_ms` | 2000 | app | 판정 뒤 자동 출발까지 대기 |
| `app.ack_timeout_ms` | 1500 | app | 손 ACK 대기 |
| `app.sort_hold_ms` | 1200 | 손 1·2 | 날개판 유지 시간 |
| `dashboard.host` | 127.0.0.1 | app | 다른 기기에서 보려면 0.0.0.0 (시험 버튼도 열림) |
| `dashboard.port` | 8000 | app | |
| `dashboard.db_path` | data/logs/pet.db | app, dashboard | SQLite 파일 (`DB_PATH`) |
| `dashboard.preview_ms` | 200 | app | 실시간 화면 갱신 간격 |

## 환경 변수 (.env)

| 변수 | 예 | 설명 |
| --- | --- | --- |
| `GATEWAY_PORT` | COM5 | 게이트웨이 micro:bit 포트 |
| `ARDUINO_PORT` | COM6 | 우노 포트 |
| `MQTT_HOST` | localhost | |
| `MQTT_PORT` | 1883 | |
| `DB_PATH` | data/logs/pet.db | 대시보드 DB 위치 (도커 안에서는 /data/pet.db) |
| `RECORD` | local | 기록 방식 (`app.record`) |
