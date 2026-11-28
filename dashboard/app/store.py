"""SQLite 저장·집계 (docs/spec/data_and_logging.md 1·2절).

나중에 Supabase로 옮길 때는 같은 메서드(add, events, summary, captures, set_label, manifest_rows)를 가진
클래스를 하나 더 만들어 바꿔 끼우면 된다. 화면·API 코드는 고치지 않아도 된다.
"""
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
CREATE TABLE IF NOT EXISTS captures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER, ts TEXT NOT NULL, bottle INTEGER,
  img TEXT NOT NULL, full TEXT,
  pred_cls TEXT, conf REAL, code TEXT, trigger TEXT,
  label TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_captures_label ON captures(label);
"""

CLASSES = ("clear_nolabel", "clear_label", "color_nolabel", "color_label")   # modes_and_states.md 4절
LABELS = CLASSES + ("exclude", "")       # exclude = 학습에서 뺌 (흐림·잘림 등), "" = 아직 확인 안 함
MANIFEST_COLUMNS = ("file", "group", "source", "license", "is_pet", "is_clear", "has_label", "has_content",
                    "split", "removed")


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def add(self, topic: str, etype: str, payload: dict) -> int:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO events (ts, topic, type, bottle, payload) VALUES (?,?,?,?,?)",
                (payload.get("ts", ""), topic, etype, payload.get("id"), json.dumps(payload, ensure_ascii=False)),
            )
            event_id = cur.lastrowid
            if etype == "JUDGMENT" and payload.get("img"):
                self.conn.execute(
                    "INSERT INTO captures (event_id, ts, bottle, img, full, pred_cls, conf, code, trigger)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (event_id, payload.get("ts", ""), payload.get("id"), payload["img"], payload.get("full"),
                     payload.get("cls"), payload.get("conf"), payload.get("code"), payload.get("trigger")),
                )
            self.conn.commit()
        return event_id

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
            caps = self.conn.execute(
                "SELECT COUNT(*), SUM(label != ''), SUM(label != '' AND label != 'exclude' AND label != pred_cls)"
                " FROM captures").fetchone()
        total = sum(codes.values())
        return {
            "bins": {c: codes.get(c, 0) for c in ("OK", "CO", "NG", "RE")},
            "total": total,
            "recheck_rate": round(codes.get("RE", 0) / total, 3) if total else 0.0,
            "stops": sum(stops.values()), "stops_by_cause": stops,
            "near_miss": warns + sum(stops.values()),
            "captures": {"total": caps[0] or 0, "labeled": caps[1] or 0, "wrong": caps[2] or 0},
        }

    # ---------- 재학습용 사진 ----------
    def captures(self, limit: int = 50, unlabeled: bool = False) -> list[dict]:
        q = "SELECT * FROM captures" + (" WHERE label = ''" if unlabeled else "") + " ORDER BY id DESC LIMIT ?"
        with self.lock:
            return [dict(r) for r in self.conn.execute(q, [limit]).fetchall()]

    def set_label(self, capture_id: int, label: str) -> bool:
        if label not in LABELS:
            raise ValueError(f"정답은 {LABELS} 중 하나")
        with self.lock:
            cur = self.conn.execute("UPDATE captures SET label = ? WHERE id = ?", (label, capture_id))
            self.conn.commit()
        return cur.rowcount == 1

    def manifest_rows(self) -> list[dict]:
        """사람이 정답을 단 사진만 training/manifest.csv 형식으로 (source=belt)."""
        with self.lock:
            rows = self.conn.execute("SELECT img, label FROM captures WHERE label != '' ORDER BY id").fetchall()
        out = []
        for img, label in rows:
            known = label in CLASSES
            out.append({
                "file": img, "group": "", "source": "belt", "license": "team", "is_pet": 1,
                "is_clear": int(label.startswith("clear")) if known else "",
                "has_label": int(label.endswith("_label")) if known else "",
                "has_content": "", "split": "", "removed": "" if known else "review",
            })
        return out
