"""Session management: create, load, save, and list ABCode sessions using SQLite."""

import sqlite3
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

from .config import DEFAULT_DB_PATH


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _conn(db_path: str) -> sqlite3.Connection:
    _ensure_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema(db_path: str) -> None:
    with _conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                name        TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                mode        TEXT NOT NULL DEFAULT 'plan',
                model       TEXT NOT NULL DEFAULT '',
                request     TEXT NOT NULL DEFAULT '',
                plan_text   TEXT NOT NULL DEFAULT '',
                subplans    TEXT NOT NULL DEFAULT '[]',
                results     TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS session_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session     TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                FOREIGN KEY (session) REFERENCES sessions(name) ON DELETE CASCADE
            );
        """)


@dataclass
class SessionData:
    name: str
    mode: str = "plan"
    model: str = ""
    request: str = ""
    plan_text: str = ""
    subplans: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    history: list = field(default_factory=list)   # [{role, content}]

    def clear_state(self) -> None:
        self.request = ""
        self.plan_text = ""
        self.subplans = []
        self.results = {}


class SessionStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        _init_schema(db_path)

    def exists(self, name: str) -> bool:
        with _conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE name = ?", (name,)
            ).fetchone()
            return row is not None

    def list_sessions(self) -> list[dict]:
        with _conn(self.db_path) as conn:
            rows = conn.execute(
                "SELECT name, created_at, updated_at, mode FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def create(self, name: str, mode: str, model: str) -> SessionData:
        now = datetime.now(timezone.utc).isoformat()
        with _conn(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (name, created_at, updated_at, mode, model) VALUES (?,?,?,?,?)",
                (name, now, now, mode, model),
            )
        return SessionData(name=name, mode=mode, model=model)

    def overwrite(self, name: str, mode: str, model: str) -> SessionData:
        self.delete(name)
        return self.create(name, mode, model)

    def delete(self, name: str) -> None:
        with _conn(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE name = ?", (name,))
            conn.execute("DELETE FROM session_history WHERE session = ?", (name,))

    def rename(self, old_name: str, new_name: str) -> bool:
        if self.exists(new_name):
            return False
        with _conn(self.db_path) as conn:
            conn.execute("UPDATE sessions SET name=? WHERE name=?", (new_name, old_name))
            conn.execute("UPDATE session_history SET session=? WHERE session=?", (new_name, old_name))
        return True

    def load(self, name: str) -> Optional[SessionData]:
        with _conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            hist_rows = conn.execute(
                "SELECT role, content FROM session_history WHERE session = ? ORDER BY id",
                (name,),
            ).fetchall()
            return SessionData(
                name=name,
                mode=row["mode"],
                model=row["model"],
                request=row["request"],
                plan_text=row["plan_text"],
                subplans=json.loads(row["subplans"]),
                results=json.loads(row["results"]),
                history=[dict(r) for r in hist_rows],
            )

    def save(self, session: SessionData) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _conn(self.db_path) as conn:
            conn.execute(
                """UPDATE sessions SET updated_at=?, mode=?, model=?, request=?,
                   plan_text=?, subplans=?, results=? WHERE name=?""",
                (
                    now,
                    session.mode,
                    session.model,
                    session.request,
                    session.plan_text,
                    json.dumps(session.subplans, ensure_ascii=False),
                    json.dumps(session.results, ensure_ascii=False),
                    session.name,
                ),
            )

    def append_message(self, session_name: str, role: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _conn(self.db_path) as conn:
            conn.execute(
                "INSERT INTO session_history (session, timestamp, role, content) VALUES (?,?,?,?)",
                (session_name, now, role, content),
            )
