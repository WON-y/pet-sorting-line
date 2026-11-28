"""휴대폰 카메라 (python -m app --phone). 휴대폰·네트워크 없이."""
import importlib
import io
import time

import pytest

from vision.bottle.phone import PhoneFeed

pytest.importorskip("fastapi")


def _jpeg(color=(40, 40, 40), size=(320, 240), box=None) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, color)
    if box:
        ImageDraw.Draw(img).rectangle(box, fill=(250, 250, 250))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_feed_token_push_and_timeout():
    feed = PhoneFeed(timeout_ms=50, token="abc")
    assert feed.check("abc") and not feed.check("abd") and not feed.check(None)
    assert not feed.connected() and feed.latest() == (0, None)
    with pytest.raises(ValueError):
        feed.push(b"not a jpeg")
    assert feed.push(_jpeg()) == 1
    assert feed.connected() and feed.info()["frames"] == 1
    time.sleep(0.08)
    assert not feed.connected()                     # 사진이 끊기면 끊김


def test_phone_server_needs_token():
    from fastapi.testclient import TestClient

    from app.phone_server import create_phone_app

    feed = PhoneFeed(token="tok")
    client = TestClient(create_phone_app(feed, {"send_width": 640, "jpeg_quality": 0.8, "interval_ms": 50}))
    assert client.get("/phone").status_code == 200
    assert client.get("/phone/config?k=bad").status_code == 403
    assert client.get("/phone/config?k=tok").json() == {"send_width": 640, "jpeg_quality": 0.8, "interval_ms": 50}
    jpeg = _jpeg()
    assert client.post("/phone/frame?k=bad", content=jpeg).status_code == 403
    assert client.post("/phone/frame?k=tok", content=b"xx").status_code == 400
    assert client.post("/phone/frame?k=tok", content=jpeg).json() == {"ok": True, "seq": 1}
    assert feed.latest() == (1, jpeg)


def test_phone_vision_detects_from_pushed_frames():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from vision.bottle.phone import PhoneVision

    feed = PhoneFeed(token="t")
    vcfg = {"camera_size": [320, 240], "model_mode": "single", "weights": "없음.pt",
            "detect": {"stable_frames": 2, "clear_frames": 2, "min_area_frac": 0.01}}
    v = PhoneVision(vcfg, feed)
    assert v.grab().status == "NO_BASELINE" and v.preview_jpeg()      # 접속 전에도 화면은 나옴
    with pytest.raises(ValueError):
        v.set_baseline()                                                # 휴대폰 없이 기준 저장 안 됨
    with pytest.raises(RuntimeError):
        v.capture()

    feed.push(_jpeg())
    v.grab()
    v.set_baseline()
    assert v.info()["phone"]["connected"] and v.size() == (320, 240)

    feed.push(_jpeg(box=(120, 80, 180, 160)))
    assert v.grab().status == "INSIDE" and not v.grab().arrived         # 같은 사진은 한 번만 셈
    feed.push(_jpeg(box=(120, 80, 180, 160)))
    assert v.grab().arrived
    full, bottle, box = v.capture()
    assert full.size == (320, 240) and box is not None

    feed.timeout_s = 0                                                  # 끊김 → 도착 신호 안 냄
    assert v.grab().status == "INSIDE" and not v.grab().arrived


def test_dashboard_phone_qr(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("DISABLE_MQTT", "1")
    import dashboard.app.main as m

    m = importlib.reload(m)
    client = TestClient(m.app)
    assert client.get("/api/phone").json() == {"enabled": False}
    assert client.get("/api/phone/qr.svg").status_code == 404

    class Runner:
        vision = type("V", (), {"feed": PhoneFeed(token="t")})()

    Runner.vision.feed.urls = ["https://192.168.0.5:8443/phone?k=t"]
    m.attach_line(Runner())
    s = client.get("/api/phone").json()
    assert s["enabled"] and s["urls"] == Runner.vision.feed.urls and not s["connected"]
    pytest.importorskip("qrcode")
    r = client.get("/api/phone/qr.svg")
    assert r.status_code == 200 and b"<svg" in r.content
    assert client.get("/api/phone/qr.svg?i=3").status_code == 404
