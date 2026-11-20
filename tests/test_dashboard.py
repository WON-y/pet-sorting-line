"""대시보드 저장·집계 (MQTT 없이)."""
import importlib

import pytest

fastapi = pytest.importorskip("fastapi")


@pytest.fixture()
def dash(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("DISABLE_MQTT", "1")
    import dashboard.app.main as m
    return importlib.reload(m)


def test_summary_counts(dash):
    from fastapi.testclient import TestClient

    for code in ["OK", "OK", "NG", "RE"]:
        dash.handle_message("pet/judgment", {"ts": "2026-11-20T10:00:00+09:00", "id": 1, "code": code})
    dash.handle_message("pet/safety", {"ts": "2026-11-20T10:01:00+09:00", "event": "STOP", "cause": "IR"})
    dash.handle_message("pet/safety", {"ts": "2026-11-20T10:02:00+09:00", "event": "WARN", "cause": "RADIO"})
    dash.handle_message("pet/state", {"run": "RUN", "mode": 1, "danger": 0, "state": "AUTO"})

    client = TestClient(dash.app)
    s = client.get("/api/summary").json()
    assert s["bins"] == {"OK": 2, "CO": 0, "NG": 1, "RE": 1}
    assert s["recheck_rate"] == 0.25
    assert s["stops"] == 1 and s["near_miss"] == 2
    assert s["state"]["state"] == "AUTO"
    assert client.get("/health").json() == {"ok": True}
    assert len(client.get("/api/events?type=STOP").json()) == 1
