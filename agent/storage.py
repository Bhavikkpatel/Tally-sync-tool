from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbound_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(entity_type, entity_id, content_hash)
);
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    detail_json TEXT
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def set_meta(self, key: str, value: Any) -> None:
        payload = json.dumps(value)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, payload),
            )

    def enqueue_outbound(self, entity_type: str, entity_id: str, payload: dict, content_hash: str) -> None:
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO outbound_queue(entity_type, entity_id, payload_json, content_hash, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id, content_hash) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    status = 'pending',
                    updated_at = excluded.updated_at
                """,
                (entity_type, entity_id, json.dumps(payload), content_hash, now, now),
            )

    def pending_outbound(self, limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM outbound_queue
                WHERE status IN ('pending', 'failed')
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_outbound(self, row_id: int, status: str, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbound_queue
                SET status = ?, last_error = ?, attempts = attempts + 1, updated_at = ?
                WHERE id = ?
                """,
                (status, error, utcnow(), row_id),
            )

    def begin_run(self, kind: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_runs(kind, started_at, status) VALUES(?, ?, 'running')",
                (kind, utcnow()),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, detail: dict | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at = ?, status = ?, detail_json = ? WHERE id = ?",
                (utcnow(), status, json.dumps(detail or {}), run_id),
            )
