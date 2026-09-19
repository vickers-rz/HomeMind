from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY,
              created_at TEXT NOT NULL,
              kind TEXT NOT NULL,
              correlation_id TEXT,
              payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_kind_created
              ON events(kind, created_at);
            CREATE TABLE IF NOT EXISTS kv (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
              id TEXT PRIMARY KEY, created_at TEXT NOT NULL, session_id TEXT,
              payload TEXT NOT NULL, inputs TEXT NOT NULL,
              execution_status TEXT NOT NULL DEFAULT 'not_executed'
            );
            CREATE INDEX IF NOT EXISTS idx_decision_time ON decisions(created_at);
            CREATE INDEX IF NOT EXISTS idx_decision_session ON decisions(session_id,created_at);
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS actions (
              id TEXT PRIMARY KEY, decision_id TEXT NOT NULL, created_at TEXT NOT NULL,
              status TEXT NOT NULL, payload TEXT NOT NULL, result TEXT
            );
            """
        )
        self.db.commit()

    def event(self, created_at: str, kind: str, payload: dict[str, Any], correlation_id: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO events(created_at,kind,correlation_id,payload) VALUES(?,?,?,?)",
            (created_at, kind, correlation_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        )
        self.db.commit()

    def set(self, key: str, value: dict[str, Any], updated_at: str) -> None:
        self.db.execute(
            "INSERT INTO kv(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), updated_at),
        )
        self.db.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def decision(self, payload, inputs):
        self.db.execute("INSERT INTO decisions(id,created_at,session_id,payload,inputs) VALUES(?,?,?,?,?)",
                        (payload['decision_id'], payload['updated_at'], payload.get('session_id'),
                         json.dumps(payload, ensure_ascii=False, allow_nan=False), json.dumps(inputs, ensure_ascii=False, allow_nan=False, default=str)))
        self.db.commit()

    def session(self, runtime, manual, now):
        with self.db:
            if runtime.get('session_id'):
                self.db.execute("INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,payload=excluded.payload",
                                (runtime['session_id'], now, json.dumps({'runtime': runtime, 'manual': manual}, ensure_ascii=False)))
            for key, value in (("runtime", runtime), ("manual_state", manual)):
                self.db.execute("INSERT INTO kv VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                                (key, json.dumps(value, ensure_ascii=False), now))

    def action(self, request):
        with self.db:
            self.db.execute("INSERT INTO actions(id,decision_id,created_at,status,payload) VALUES(?,?,?,'requested',?)",
                            (request['id'], request['decision_id'], request['created_at'], json.dumps(request)))
            self.db.execute("UPDATE decisions SET execution_status='requested' WHERE id=?", (request['decision_id'],))

    def result(self, payload):
        with self.db:
            self.db.execute("UPDATE actions SET status=?,result=? WHERE id=?", (payload.get('status', 'unknown'), json.dumps(payload), payload.get('request_id')))
            self.db.execute("UPDATE decisions SET execution_status=? WHERE id=(SELECT decision_id FROM actions WHERE id=?)", (payload.get('status', 'unknown'), payload.get('request_id')))

    def cleanup(self, now, active_session=None):
        cutoff = (now-timedelta(days=90)).isoformat()
        with self.db:
            self.db.execute("DELETE FROM decisions WHERE created_at < ? AND (session_id IS NULL OR session_id != ?)", (cutoff, active_session or ''))
            self.db.execute("DELETE FROM actions WHERE created_at < ? AND decision_id NOT IN (SELECT id FROM decisions)", (cutoff,))
            self.db.execute("DELETE FROM sessions WHERE updated_at < ? AND id != ?", (cutoff, active_session or ''))
            self.db.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))

    def export(self, since=None, until=None, session_id=None):
        clauses, args = [], []
        for clause, value in (("created_at >= ?", since), ("created_at < ?", until), ("session_id = ?", session_id)):
            if value:
                clauses.append(clause); args.append(value)
        query = "SELECT payload, inputs, execution_status FROM decisions" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY created_at"
        for payload, inputs, status in self.db.execute(query, args):
            yield {**json.loads(payload), "inputs": json.loads(inputs), "execution_status": status}
