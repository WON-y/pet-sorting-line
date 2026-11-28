"""휴대폰 카메라 전용 https 서버 (python -m app --phone).

휴대폰 브라우저는 https에서만 카메라를 허용하므로 자체 서명 인증서로 따로 띄운다.
대시보드(시험 버튼 있음)는 노트북 안(127.0.0.1)에 그대로 두고, 같은 와이파이에는 이 서버만 연다.
이 서버가 하는 일은 두 가지뿐이다: 휴대폰 페이지 보여 주기, 사진 받기 (QR 주소의 토큰이 맞을 때만).
"""
from __future__ import annotations

import logging
import socket
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from vision.bottle.phone import MAX_FRAME_BYTES, PhoneFeed

log = logging.getLogger("app.phone")
PAGE = Path(__file__).resolve().parents[1] / "dashboard" / "static" / "phone.html"


def lan_ips(host_ip: str = "") -> list[str]:
    """휴대폰이 접속할 노트북 주소 후보. 기본 경로의 주소를 맨 앞에 (UDP connect는 패킷을 보내지 않음)."""
    from vision.webtest.__main__ import lan_addresses

    ips = [host_ip] if host_ip else []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    ips += lan_addresses()
    return [ip for i, ip in enumerate(ips) if ip and not ip.startswith("127.") and ip not in ips[:i]]


def create_phone_app(feed: PhoneFeed, pcfg: dict) -> FastAPI:
    app = FastAPI(title="pet-sorting-line phone camera", docs_url=None, redoc_url=None, openapi_url=None)

    def _check(k: str | None) -> None:
        if not feed.check(k):
            raise HTTPException(403, "주소가 맞지 않습니다. 대시보드의 QR을 다시 찍으세요")

    @app.get("/phone")
    def page() -> FileResponse:
        return FileResponse(PAGE, headers={"Cache-Control": "no-store"})

    @app.get("/phone/config")
    def config(k: str | None = None) -> dict:
        _check(k)
        return {"send_width": int(pcfg.get("send_width", 1280)), "jpeg_quality": float(pcfg.get("jpeg_quality", 0.85)),
                "interval_ms": int(pcfg.get("interval_ms", 100))}

    @app.post("/phone/frame")
    async def frame(request: Request, k: str | None = None) -> dict:
        _check(k)
        if int(request.headers.get("content-length") or 0) > MAX_FRAME_BYTES:
            raise HTTPException(413, "사진이 너무 큽니다")
        try:
            seq = feed.push(await request.body())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "seq": seq}

    return app


def start_phone_server(feed: PhoneFeed, pcfg: dict):
    """0.0.0.0:<phone.port> https로 띄우고, 휴대폰 접속 주소를 feed.urls에 넣는다."""
    import uvicorn

    from vision.webtest.__main__ import ensure_self_signed_cert

    port = int(pcfg.get("port", 8443))
    ips = lan_ips(str(pcfg.get("host_ip") or ""))
    cert, key = ensure_self_signed_cert(ips)
    feed.urls = [f"https://{ip}:{port}/phone?k={feed.token}" for ip in ips]
    config = uvicorn.Config(create_phone_app(feed, pcfg), host="0.0.0.0", port=port, log_level="warning",
                            ssl_certfile=str(cert), ssl_keyfile=str(key))
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="phone", daemon=True).start()
    if not ips:
        log.warning("와이파이 주소를 찾지 못했습니다. settings.yaml phone.host_ip에 노트북 주소를 적으세요")
    for url in feed.urls:
        log.info("휴대폰 카메라 주소: %s", url)
    return server
