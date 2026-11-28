"""대시보드 저장·집계·사진 (MQTT 없이)."""
import importlib

import pytest

fastapi = pytest.importorskip("fastapi")


@pytest.fixture()
def dash(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("CAPTURE_DIR", str(tmp_path / "cap"))
    monkeypatch.setenv("DISABLE_MQTT", "1")
    import dashboard.app.main as m
    return importlib.reload(m)


def test_summary_counts(dash):
    from fastapi.testclient import TestClient

    for code in ["OK", "OK", "NG", "RE"]:
        dash.handle_message("pet/judgment", {"ts": "2026-11-20T10:00:00+09:00", "id": 1, "code": code})
    dash.handle_message("pet/safety", {"ts": "2026-11-20T10:01:00+09:00", "event": "STOP", "cause": "MODE"})
    dash.handle_message("pet/safety", {"ts": "2026-11-20T10:02:00+09:00", "event": "WARN", "cause": "RADIO"})
    dash.handle_message("pet/state", {"run": "RUN", "mode": 1, "danger": 0, "state": "AUTO"})

    client = TestClient(dash.app)
    s = client.get("/api/summary").json()
    assert s["bins"] == {"OK": 2, "CO": 0, "NG": 1, "RE": 1}
    assert s["recheck_rate"] == 0.25
    assert s["stops"] == 1 and s["near_miss"] == 2
    assert s["state"]["state"] == "AUTO" and s["line"] is False
    assert client.get("/health").json() == {"ok": True}
    assert len(client.get("/api/events?type=STOP").json()) == 1
    assert client.get("/api/line").status_code == 503      # 라인 없이 띄운 대시보드 (도커 등)


def test_captures_label_and_manifest(dash, tmp_path):
    from fastapi.testclient import TestClient

    (tmp_path / "cap" / "20261126").mkdir(parents=True)
    (tmp_path / "cap" / "20261126" / "W_a_crop.jpg").write_bytes(b"\xff\xd8jpeg")
    for i, cls in enumerate(["clear_label", "clear_nolabel", "color_label"]):
        dash.handle_message("pet/judgment", {"ts": "2026-11-26T10:00:00+09:00", "id": i, "cls": cls, "code": "NG",
                                             "conf": 0.9, "img": "20261126/W_a_crop.jpg", "full": "x_full.jpg"})
    client = TestClient(dash.app)
    caps = client.get("/api/captures").json()
    assert len(caps) == 3 and caps[0]["label"] == ""
    ids = [c["id"] for c in caps]                           # 최신부터: color_label, clear_nolabel, clear_label
    assert client.post(f"/api/captures/{ids[2]}/label", json={"label": "clear_label"}).status_code == 200
    assert client.post(f"/api/captures/{ids[1]}/label", json={"label": "clear_label"}).status_code == 200  # 오판정
    assert client.post(f"/api/captures/{ids[0]}/label", json={"label": "exclude"}).status_code == 200
    assert client.post(f"/api/captures/{ids[0]}/label", json={"label": "dog"}).status_code == 400
    assert client.post("/api/captures/999/label", json={"label": "exclude"}).status_code == 404
    assert len(client.get("/api/captures?unlabeled=true").json()) == 0
    assert client.get("/api/summary").json()["captures"] == {"total": 3, "labeled": 3, "wrong": 1}

    lines = client.get("/api/captures.csv").text.strip().split("\n")
    assert lines[0] == "file,group,source,license,is_pet,is_clear,has_label,has_content,split,removed"
    assert lines[1] == "20261126/W_a_crop.jpg,,belt,team,1,1,1,,,"
    assert lines[3].endswith(",review")                     # 학습에서 뺀 사진

    assert client.get("/captures/20261126/W_a_crop.jpg").status_code == 200
    assert client.get("/captures/../t.db").status_code == 404   # 사진 폴더 밖은 못 읽음


def test_labels_match_protocol_classes():
    from common.protocol import CLASS_TO_CODE
    from dashboard.app.store import CLASSES

    assert set(CLASSES) == set(CLASS_TO_CODE)


def test_line_actions_with_sim_belt(dash, tmp_path):
    from fastapi.testclient import TestClient

    from app.controller import LineController
    from app.line import LineRunner, LocalRecorder
    from app.mock import MockVision
    from app.sim_belt import SimBelt

    belt = SimBelt()
    r = LineRunner({"app": {}, "vision": {}}, MockVision(belt), belt, LineController(),
                   LocalRecorder(dash.handle_message), capture_dir=tmp_path / "cap")
    dash.attach_line(r)

    import threading
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            r.step()

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    try:
        client = TestClient(dash.app)
        assert client.post("/api/line/reset").json()["result"] == "OK"
        assert client.post("/api/line/baseline").json()["result"] == "LEARNING"   # 벨트가 돌면 여러 장
        assert client.get("/api/line").json()["vision"]["baseline_check"]["kind"] == "multi"
        assert client.post("/api/line/mode", json={"mode": 3}).status_code == 200
        assert client.post("/api/line/baseline").json()["result"] == "SINGLE"     # 멈춰 있으면 1장
        assert belt.run == "STOP"
        assert client.post("/api/line/reset").json()["result"] == "MODE_NOT_1_OR_2"
        assert client.post("/api/line/roi", json={"roi": [10, 10, 300, 300]}).status_code == 200
        assert client.post("/api/line/roi", json={"roi": [1, 2]}).status_code == 400
        assert client.get("/api/line").json()["belt"]["sim"] is True
        r.is_sim = False                                    # 실제 우노라면 재가동·모드는 막힘
        assert client.post("/api/line/reset").status_code == 403
        assert client.post("/api/line/mode", json={"mode": 1}).status_code == 403
        assert client.post("/api/line/hold").status_code == 200
    finally:
        stop.set()
        th.join(2)
        dash.attach_line(None)
