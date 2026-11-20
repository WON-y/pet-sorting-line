"""대시보드: MQTT 구독 → SQLite 저장, API와 정적 화면 제공 (docs/spec/protocol.md 5·6절)."""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .store import Store

log = logging.getLogger("dashboard")
STATIC = Path(__file__).resolve().parents[1] / "static"
PREFIX = os.environ.get("TOPIC_PREFIX", "pet")
LEAF_TO_TYPE = {"judgment": "JUDGMENT", "sort": "SORT", "mode": "MODE", "hand": "HAND"}

store = Store(os.environ.get("DB_PATH", "pet.db"))
latest_state: dict = {}


def handle_message(topic: str, payload: dict) -> None:
    """MQTT 메시지 한 건 처리. 시험에서도 직접 부른다."""
    global latest_state
    leaf = topic.split("/")[1] if "/" in topic else topic
    if leaf == "state":
        latest_state = payload
        return
    etype = str(payload.get("event", "ERROR")) if leaf == "safety" else LEAF_TO_TYPE.get(leaf, "ERROR")
    store.add(topic, etype, payload)


def start_mqtt() -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log.warning("paho-mqtt 없음: MQTT 구독 안 함")
        return

    def on_connect(client, *_):
        client.subscribe(f"{PREFIX}/#", qos=1)

    def on_message(_client, _userdata, msg):
        try:
            handle_message(msg.topic, json.loads(msg.payload))
        except Exception as e:  # 잘못된 메시지 하나로 대시보드가 죽지 않게
            log.warning("메시지 처리 실패 %s: %s", msg.topic, e)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pet-dashboard")
    client.on_connect, client.on_message = on_connect, on_message
    try:
        client.connect(os.environ.get("MQTT_HOST", "localhost"), int(os.environ.get("MQTT_PORT", 1883)))
        client.loop_start()
    except Exception as e:
        log.warning("MQTT 연결 실패: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("DISABLE_MQTT") != "1":
        start_mqtt()
    yield


app = FastAPI(title="pet-sorting-line dashboard", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/summary")
def summary() -> dict:
    return store.summary() | {"state": latest_state}


@app.get("/api/events")
def events(type: str | None = None, limit: int = 50) -> list[dict]:
    return store.events(type, min(limit, 500))


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
