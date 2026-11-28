# 모의(mock) 실행 전용 이미지. 실제 하드웨어 실행은 노트북에서 python -m app (웹캠·USB 때문)
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY communication ./communication
COPY vision ./vision
COPY app ./app
COPY config ./config
# 도커에서는 대시보드가 따로 있으므로 MQTT로 기록하고 웹 서버는 켜지 않는다
ENV MQTT_HOST=mqtt MQTT_PORT=1883 RECORD=mqtt
CMD ["python", "-m", "app", "--mock", "--no-web"]
