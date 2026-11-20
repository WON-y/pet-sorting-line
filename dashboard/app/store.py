"""SQLite 저장·집계 (docs/spec/data_and_logging.md 1·2절)."""
from __future__ import annotations

import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, topic TEXT NOT NULL, type TEXT NOT NULL,
  bottle INTEGER, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
"""


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def add(self, topic: str, etype: str, payload: dict) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO events (ts, topic, type, bottle, payload) VALUES (?,?,?,?,?)",
                (payload.get("ts", ""), topic, etype, payload.get("id"), json.dumps(payload, ensure_ascii=False)),
            )
            self.conn.commit()

    def events(self, etype: str | None = None, limit: int = 50) -> list[dict]:
        q, args = "SELECT * FROM events", []
        if etype:
            q, args = q + " WHERE type = ?", [etype]
        q += " ORDER BY id DESC LIMIT ?"
        with self.lock:
            rows = self.conn.execute(q, [*args, limit]).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]

    def summary(self) -> dict:
        with self.lock:
            codes = {r[0]: r[1] for r in self.conn.execute(
                "SELECT json_extract(payload,'$.code'), COUNT(*) FROM events WHERE type='JUDGMENT' GROUP BY 1")}
            stops = {r[0]: r[1] for r in self.conn.execute(
                "SELECT json_extract(payload,'$.cause'), COUNT(*) FROM events WHERE type='STOP' GROUP BY 1")}
            warns = self.conn.execute("SELECT COUNT(*) FROM events WHERE type='WARN'").fetchone()[0]
        total = sum(codes.values())
        return {
            "bins": {c: codes.get(c, 0) for c in ("OK", "CO", "NG", "RE")},
            "total": total,
            "recheck_rate": round(codes.get("RE", 0) / total, 3) if total else 0.0,
            "stops": sum(stops.values()), "stops_by_cause": stops,
            "near_miss": warns + sum(stops.values()),
        }
