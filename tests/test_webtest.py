"""카메라 인식 웹 테스트 (가짜 모델, ultralytics 없이)."""
import io

import pytest
from PIL import Image

from common.config import load_settings
from vision.webtest.recognizer import Recognizer, clamp_roi

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


class FakeModel:
    def __init__(self, names, top):
        self.names, self.top, self.seen = names, top, []

    def predict_topk(self, img, k):
        self.seen.append(img.size)
        return self.top[:k]


FOUR = ["clear_label", "clear_nolabel", "color_label", "color_nolabel"]


def vision_cfg(roi=None):
    return load_settings()["vision"] | {"roi": roi}


def jpeg(w=640, h=480):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 200, 200)).save(buf, "JPEG")
    return buf.getvalue()


def client(model, roi=None):
    from fastapi.testclient import TestClient

    from vision.webtest.server import create_app

    return TestClient(create_app(Recognizer(model, "fake.pt", vision_cfg(roi)), interval_ms=500))


def test_clamp_roi():
    assert clamp_roi(None, 640, 480) is None
    assert clamp_roi([100, 50, 300, 250], 640, 480) == [100, 50, 300, 250]
    assert clamp_roi([600, 400, 2000, 2000], 640, 480) == [600, 400, 640, 480]
    assert clamp_roi([700, 500, 800, 600], 640, 480) is None   # 사진 밖


def test_custom_model_gives_code():
    c = client(FakeModel(FOUR, [("clear_label", 0.93), ("clear_nolabel", 0.05)]))
    assert c.get("/api/info").json()["custom"] is True
    r = c.post("/api/predict", content=jpeg(), headers={"Content-Type": "image/jpeg"}).json()
    assert (r["cls"], r["code"], r["size"]) == ("clear_label", "NG", [640, 480])
    assert r["top"][0] == {"cls": "clear_label", "conf": 0.93}


def test_low_confidence_is_recheck():
    c = client(FakeModel(FOUR, [("clear_nolabel", 0.55), ("clear_label", 0.40)]))
    r = c.post("/api/predict", content=jpeg()).json()
    assert r["code"] == "RE"


def test_generic_model_has_no_code():
    c = client(FakeModel(["water_bottle", "cup"], [("water_bottle", 0.7), ("cup", 0.2)]))
    assert c.get("/api/info").json()["custom"] is False
    r = c.post("/api/predict", content=jpeg()).json()
    assert r["code"] is None and r["cls"] == "water_bottle"


def test_roi_toggle_and_preprocess_size():
    m = FakeModel(FOUR, [("clear_nolabel", 0.9)])
    c = client(m, roi=[100, 50, 300, 250])
    assert c.post("/api/predict?roi=1", content=jpeg()).json()["roi"] == [100, 50, 300, 250]
    assert c.post("/api/predict?roi=0", content=jpeg()).json()["roi"] is None
    assert m.seen == [(224, 224), (224, 224)]   # 학습과 같은 레터박스 크기


def test_bad_upload():
    c = client(FakeModel(FOUR, [("clear_nolabel", 0.9)]))
    assert c.post("/api/predict", content=b"").status_code == 400
    assert c.post("/api/predict", content=b"not an image").status_code == 400
    assert c.get("/").status_code == 200


class FakeCam:
    """OpenCV 없이 쓰는 가짜 웹캠. index 3은 '열 수 없음'."""
    opened: list = []

    def __init__(self, index):
        if index == 3:
            raise RuntimeError("웹캠 3번을 열 수 없습니다")
        FakeCam.opened.append(index)

    def read_rgb(self):
        import numpy as np

        return np.full((480, 640, 3), 128, dtype=np.uint8)


def test_server_camera_frame():
    pytest.importorskip("numpy")
    from fastapi.testclient import TestClient

    from vision.webtest.server import create_app
    from vision.webtest.server_camera import ServerCamera

    FakeCam.opened = []
    rec = Recognizer(FakeModel(FOUR, [("clear_nolabel", 0.9)]), "fake.pt", vision_cfg())
    c = TestClient(create_app(rec, 500, camera_index=1, server_camera=ServerCamera(FakeCam)))
    assert c.get("/api/info").json()["camera_index"] == 1

    r = c.get("/api/server_camera/frame.jpg")              # 기본 번호(1번)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(r.content)).size == (640, 480)
    c.get("/api/server_camera/frame.jpg?index=1")           # 같은 번호는 다시 열지 않음
    c.get("/api/server_camera/frame.jpg?index=0")           # 번호를 바꾸면 새로 연다
    assert FakeCam.opened == [1, 0]

    assert c.get("/api/server_camera/frame.jpg?index=3").status_code == 503   # 열 수 없음
    assert c.get("/api/server_camera/frame.jpg?index=7").status_code == 400   # 범위 밖
    # 받은 화면을 그대로 인식에 넣을 수 있어야 한다
    assert c.post("/api/predict", content=r.content).json()["code"] == "OK"
