FROM python:3.12-slim
WORKDIR /srv
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dashboard/app ./dashboard/app
COPY dashboard/static ./dashboard/static
ENV DB_PATH=/data/pet.db MQTT_HOST=mqtt MQTT_PORT=1883
EXPOSE 8000
CMD ["uvicorn", "dashboard.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
