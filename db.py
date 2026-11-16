from __future__ import annotations
import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any
import core
SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user TEXT NOT NULL,
  at INTEGER NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user, id);
CREATE TABLE IF NOT EXISTS models(
  user TEXT PRIMARY KEY,
  json TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cats(
  user TEXT NOT NULL,
  node TEXT NOT NULL,
  tier TEXT NOT NULL,
  at INTEGER NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY(user, node, tier)
);
CREATE TABLE IF NOT EXISTS ai_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user TEXT,
  at INTEGER,
  input TEXT,
  output TEXT,
  ok INTEGER,
  latency_ms INTEGER,
  error TEXT
);
CREATE TABLE IF NOT EXISTS snapshots(
  user TEXT NOT NULL,
  upto INTEGER NOT NULL,
  json TEXT NOT NULL,
  at INTEGER NOT NULL,
  PRIMARY KEY(user, upto)
);
"""
class Db:
    def __init__(self, path: str | Path = "data/app.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)
        self.con.commit()
    def append(self, user: str, ev: dict[str, Any]) -> int:
        cur = self.con.execute(
            "INSERT INTO events(user, at, kind, payload) VALUES(?,?,?,?)",
            (user, int(ev.get("at") or 0), str(ev.get("type") or "?"), json.dumps(ev, ensure_ascii=False)),
        )
        self.con.commit()
        return int(cur.lastrowid)
    def events(self, user: str, after_id: int = 0) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT id, payload FROM events WHERE user=? AND id>? ORDER BY id", (user, after_id)
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]
    def count(self, user: str) -> int:
        return int(self.con.execute("SELECT COUNT(*) FROM events WHERE user=?", (user,)).fetchone()[0])
    def load_model(self, user: str) -> dict[str, Any]:
        row = self.con.execute("SELECT json FROM models WHERE user=?", (user,)).fetchone()
        return json.loads(row["json"]) if row else {}
    def save_model(self, user: str, model: dict[str, Any]) -> None:
        self.con.execute(
            "INSERT INTO models(user, json, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(user) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at",
            (user, json.dumps(model, ensure_ascii=False), int(time.time() * 1000)),
        )
        self.con.commit()
    def add_cards(self, user: str, cards: list[dict[str, Any]]) -> int:
        n = 0
        for c in cards:
            cur = self.con.execute(
                "INSERT OR IGNORE INTO cats(user, node, tier, at, source) VALUES(?,?,?,?,?)",
                (user, c["node"], c["tier"], int(c.get("at") or 0), str(c.get("source") or "rule")),
            )
            n += int(cur.rowcount > 0)
        self.con.commit()
        return n
    def cards(self, user: str) -> list[dict[str, Any]]:
        rows = self.con.execute("SELECT node, tier, at, source FROM cats WHERE user=? ORDER BY at", (user,)).fetchall()
        return [dict(r) for r in rows]
    def maybe_snapshot(self, user: str, state: core.State, every: int = 20) -> bool:
        n = self.count(user)
        if n == 0 or n % every != 0:
            return False
        upto = int(self.con.execute("SELECT MAX(id) FROM events WHERE user=?", (user,)).fetchone()[0] or 0)
        self.con.execute(
            "INSERT OR REPLACE INTO snapshots(user, upto, json, at) VALUES(?,?,?,?)",
            (user, upto, json.dumps(asdict(state), ensure_ascii=False), int(time.time() * 1000)),
        )
        self.con.commit()
        return True
    def restore(self, user: str) -> core.State:
        row = self.con.execute(
            "SELECT upto, json FROM snapshots WHERE user=? ORDER BY upto DESC LIMIT 1", (user,)
        ).fetchone()
        if row:
            state = core.State(**json.loads(row["json"]))
            after = int(row["upto"])
        else:
            state = core.State(user=user)
            after = 0
        for ev in self.events(user, after):
            state, _ = core.reduce(state, ev)
        return state
    def log_ai(
        self,
        user: str,
        at: int,
        decision: dict[str, Any],
        ok: bool,
        latency_ms: int,
        error: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.con.execute(
            "INSERT INTO ai_logs(user, at, input, output, ok, latency_ms, error) VALUES(?,?,?,?,?,?,?)",
            (
                user,
                int(at),
                json.dumps(context or {}, ensure_ascii=False, default=str),
                json.dumps(decision, ensure_ascii=False, default=str),
                int(ok),
                int(latency_ms),
                error,
            ),
        )
        self.con.commit()
    def close(self) -> None:
        self.con.close()
