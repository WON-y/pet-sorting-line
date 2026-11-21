"""웹 테스트 서버 (FastAPI). 휴대폰·웹캠 사진을 받아 인식 결과를 돌려준다.

시험용 도구다. 라인을 제어하지 않고, MQTT로 판정을 보내지도 않는다 (대시보드 통계를 더럽히지 않게).
"""
from __future__ import annotations

import io
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from .recognizer import Recognizer
from .server_camera import ServerCamera

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 휴대폰 원본 사진도 들어가는 크기
MAX_CAMERA_INDEX = 3                  # 화면에서 고를 수 있는 웹캠 번호 0~3


def create_app(recognizer: Recognizer, interval_ms: int, camera_index: int = 0,
               server_camera: ServerCamera | None = None) -> FastAPI:
    cam = server_camera or ServerCamera()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        cam.close()   # 서버를 끄면 웹캠을 놓아 준다

    app = FastAPI(title="pet-sorting-line camera test", lifespan=lifespan)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/info")
    def info() -> dict:
        return recognizer.info() | {
            "interval_ms": interval_ms,
            "camera_index": camera_index,
            "camera_indexes": list(range(MAX_CAMERA_INDEX + 1)),
        }

    @app.get("/api/server_camera/frame.jpg")
    def server_frame(index: int = camera_index) -> Response:
        """노트북 USB 웹캠의 현재 화면 한 장 (브라우저 권한 필요 없음)."""
        if not 0 <= index <= MAX_CAMERA_INDEX:
            raise HTTPException(400, "웹캠 번호가 범위를 벗어났습니다")
        try:
            jpeg = cam.frame_jpeg(index)
        except Exception as e:
            raise HTTPException(503, f"노트북 웹캠 {index}번을 읽을 수 없습니다: {e}") from e
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/predict")
    async def predict(request: Request, roi: int = 1) -> dict:
        body = await request.body()
        if not body:
            raise HTTPException(400, "사진이 비어 있습니다")
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "사진이 너무 큽니다")
        try:
            img = Image.open(io.BytesIO(body))
            img.load()
        except (UnidentifiedImageError, OSError) as e:
            raise HTTPException(400, "사진 형식을 읽을 수 없습니다") from e
        # 모델 계산은 오래 걸리므로 별도 스레드에서 (서버가 다른 요청을 계속 받게)
        return await run_in_threadpool(recognizer.predict, img, bool(roi))

    return app
