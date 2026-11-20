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
ENV MQTT_HOST=mqtt MQTT_PORT=1883
CMD ["python", "-m", "app", "--mock"]
