"""대시보드: 기록 저장(SQLite), API, 웹 화면 (docs/spec/protocol.md 5·6절).

두 가지로 쓸 수 있다.
1) 노트북 하나 (기본): `python -m app`이 이 앱을 같은 프로그램 안에서 띄우고, handle_message로 바로 기록한다.
   attach_line()으로 라인 실행기를 붙이면 실시간 화면·시험 버튼(/api/line/...)이 열린다.
2) 도커 (선택): uvicorn으로 따로 띄우면 MQTT `pet/#`을 구독해 기록한다. 이때 /api/line은 503.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .store import LABELS, MANIFEST_COLUMNS, Store

log = logging.getLogger("dashboard")
STATIC = Path(__file__).resolve().parents[1] / "static"
PREFIX = os.environ.get("TOPIC_PREFIX", "pet")
LEAF_TO_TYPE = {"judgment": "JUDGMENT", "sort": "SORT", "mode": "MODE", "hand": "HAND"}

store: Store
capture_dir: Path
latest_state: dict = {}
line = None            # app.line.LineRunner (노트북 하나로 실행할 때만)


def init(db_path: str, captures: str = "data/captures") -> None:
    """DB 파일과 사진 폴더를 정한다. 폴더가 없으면 만든다."""
    global store, capture_dir
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    store = Store(db_path)
    capture_dir = Path(captures)


def attach_line(runner) -> None:
    global line
    line = runner


init(os.environ.get("DB_PATH", "data/logs/pet.db"), os.environ.get("CAPTURE_DIR", "data/captures"))


def handle_message(topic: str, payload: dict) -> None:
    """기록 한 건 처리 (MQTT 메시지 또는 같은 프로그램의 app). 시험에서도 직접 부른다."""
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
    # 노트북 하나로 실행할 때(line이 붙어 있음)는 MQTT를 구독하지 않는다 (기록이 두 번 들어가지 않게)
    if os.environ.get("DISABLE_MQTT") != "1" and line is None:
        start_mqtt()
    yield


app = FastAPI(title="pet-sorting-line dashboard", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/summary")
def summary() -> dict:
    return store.summary() | {"state": latest_state, "line": line is not None}


@app.get("/api/events")
def events(type: str | None = None, limit: int = 50) -> list[dict]:
    return store.events(type, min(limit, 500))


# ---------- 촬영 사진 (재학습용) ----------
@app.get("/api/captures")
def captures(limit: int = 24, unlabeled: bool = False) -> list[dict]:
    return store.captures(min(limit, 500), unlabeled)


@app.post("/api/captures/{capture_id}/label")
def set_label(capture_id: int, label: str = Body(..., embed=True)) -> dict:
    if label not in LABELS:
        raise HTTPException(400, f"정답은 {LABELS} 중 하나")
    if not store.set_label(capture_id, label):
        raise HTTPException(404, "사진이 없습니다")
    return {"ok": True}


@app.get("/api/captures.csv")
def captures_csv() -> Response:
    """정답을 단 사진 목록 (training/manifest.csv와 같은 열)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(store.manifest_rows())
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=belt_manifest.csv"})


@app.get("/captures/{path:path}")
def capture_file(path: str) -> FileResponse:
    root = capture_dir.resolve()
    f = (root / path).resolve()
    if not f.is_relative_to(root) or not f.is_file() or f.suffix.lower() != ".jpg":
        raise HTTPException(404, "사진이 없습니다")
    return FileResponse(f, media_type="image/jpeg")


# ---------- 라인 실시간 화면·시험 버튼 (노트북 하나로 실행할 때만) ----------
def _line():
    if line is None:
        raise HTTPException(503, "라인이 연결되지 않았습니다 (python -m app 으로 실행)")
    return line


@app.get("/api/line")
def line_status() -> dict:
    return _line().status()


@app.get("/api/line/frame.jpg")
def line_frame() -> Response:
    jpeg = _line().preview()
    if not jpeg:
        raise HTTPException(503, "아직 화면이 없습니다")
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def _phone_feed():
    """python -m app --phone 일 때만 있다 (vision/bottle/phone.py PhoneFeed)."""
    return getattr(line.vision, "feed", None) if line is not None else None


@app.get("/api/phone")
def phone_status() -> dict:
    feed = _phone_feed()
    return {"enabled": False} if feed is None else {"enabled": True} | feed.info()


@app.get("/api/phone/qr.svg")
def phone_qr(i: int = 0) -> Response:
    """휴대폰 접속 주소(토큰 포함) QR. 대시보드 화면에서만 보여 준다."""
    feed = _phone_feed()
    if feed is None or not 0 <= i < len(feed.urls):
        raise HTTPException(404, "휴대폰 카메라 모드가 아닙니다 (python -m app --phone)")
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError as e:
        raise HTTPException(503, "qrcode 패키지가 없습니다 (pip install -r requirements-hw.txt)") from e
    svg = qrcode.make(feed.urls[i], image_factory=SvgPathImage, box_size=10, border=2).to_string()
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.post("/api/line/{action}")
def line_action(action: str, body: Annotated[dict | None, Body()] = None) -> dict:
    """시험 버튼. 실제 우노가 연결돼 있으면 재가동(reset)·모드는 막는다 (재가동은 리셋 버튼으로만)."""
    r = _line()
    body = body or {}
    from app.line import now_ms

    sim = r.is_sim
    try:
        if action == "baseline":
            r.call(r.vision.set_baseline)
        elif action == "roi":
            roi = body.get("roi")
            if roi is not None and (not isinstance(roi, list) or len(roi) != 4):
                raise HTTPException(400, "roi는 [x1, y1, x2, y2] 또는 null")
            r.call(lambda: r.vision.set_roi(roi))
        elif action == "capture":
            r.call(lambda: r.execute(r.ctl.on_manual(now_ms())))
        elif action == "hold":
            r.call(lambda: r.execute([("arduino", "HOLD")]))
        elif action == "reset":
            if not sim:
                raise HTTPException(403, "실제 우노는 리셋 버튼으로만 재가동합니다")
            return {"ok": True, "result": r.call(r.belt.press_reset)}
        elif action == "mode":
            if not sim:
                raise HTTPException(403, "실제 라인의 모드는 손 3 수신호·카드로만 바꿉니다")
            mode = int(body.get("mode", 0))
            r.call(lambda: r.belt.set_mode(mode))
        else:
            raise HTTPException(404, "모르는 동작")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
