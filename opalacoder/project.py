"""Project management: create, load, save, and list OpalaCoder projects using SQLite."""

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
            CREATE TABLE IF NOT EXISTS projects (
                name            TEXT PRIMARY KEY,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                mode            TEXT NOT NULL DEFAULT 'plan',
                model           TEXT NOT NULL DEFAULT '',
                project_name    TEXT NOT NULL DEFAULT '',
                project_path    TEXT NOT NULL DEFAULT '',
                skills          TEXT NOT NULL DEFAULT '["opalacoder"]',
                description     TEXT NOT NULL DEFAULT '',
                request         TEXT NOT NULL DEFAULT '',
                plan_text       TEXT NOT NULL DEFAULT '',
                subplans        TEXT NOT NULL DEFAULT '[]',
                results         TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS project_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project     TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                FOREIGN KEY (project) REFERENCES projects(name) ON DELETE CASCADE
            );
        """)
        
        # Migração: tentar adicionar core_memory caso não exista
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN core_memory TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass


@dataclass
class ProjectData:
    name: str
    mode: str = "plan"
    model: str = ""
    project_name: str = ""
    project_path: str = ""
    skills: list = field(default_factory=lambda: ["opalacoder"])
    description: str = ""
    request: str = ""
    plan_text: str = ""
    subplans: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    core_memory: str = ""
    history: list = field(default_factory=list)   # [{role, content}]

    def clear_state(self) -> None:
        self.request = ""
        self.plan_text = ""
        self.subplans = []
        self.results = {}

    def context_header(self) -> str:
        """Returns a project context string to prepend to every prompt."""
        name = self.project_name or self.name
        path = self.project_path or "(unspecified)"
        return f"[PROJECT: {name} | PATH: {path}]\n"


# Backward-compat alias so existing imports of SessionData still work during migration
SessionData = ProjectData


class ProjectStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        _init_schema(db_path)

    def exists(self, name: str) -> bool:
        with _conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM projects WHERE name = ?", (name,)
            ).fetchone()
            return row is not None

    def list_projects(self) -> list[dict]:
        with _conn(self.db_path) as conn:
            rows = conn.execute(
                "SELECT name, project_name, project_path, created_at, updated_at, mode FROM projects ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def create(self, name: str, mode: str, model: str, project_name: str = "", project_path: str = "", skills: list = None, description: str = "") -> ProjectData:
        now = datetime.now(timezone.utc).isoformat()
        _skills = skills if skills is not None else ["opalacoder"]
        if "opalacoder" not in _skills:
            _skills = ["opalacoder"] + _skills
        with _conn(self.db_path) as conn:
            conn.execute(
                "INSERT INTO projects (name, created_at, updated_at, mode, model, project_name, project_path, skills, description, core_memory) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (name, now, now, mode, model, project_name, project_path, json.dumps(_skills), description, ""),
            )
        return ProjectData(name=name, mode=mode, model=model, project_name=project_name, project_path=project_path, skills=_skills, description=description, core_memory="")

    def overwrite(self, name: str, mode: str, model: str, project_name: str = "", project_path: str = "", skills: list = None, description: str = "") -> ProjectData:
        self.delete(name)
        return self.create(name, mode, model, project_name, project_path, skills, description)

    def delete(self, name: str) -> None:
        with _conn(self.db_path) as conn:
            conn.execute("DELETE FROM projects WHERE name = ?", (name,))
            conn.execute("DELETE FROM project_history WHERE project = ?", (name,))
        try:
            from .archival import clear_archival
            clear_archival(name)
        except Exception:
            pass

    def rename(self, old_name: str, new_name: str) -> bool:
        if self.exists(new_name):
            return False
        with _conn(self.db_path) as conn:
            conn.execute("UPDATE projects SET name=? WHERE name=?", (new_name, old_name))
            conn.execute("UPDATE project_history SET project=? WHERE project=?", (new_name, old_name))
        return True

    def load(self, name: str) -> Optional[ProjectData]:
        with _conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            hist_rows = conn.execute(
                "SELECT role, content FROM project_history WHERE project = ? ORDER BY id",
                (name,),
            ).fetchall()
            return ProjectData(
                name=name,
                mode=row["mode"],
                model=row["model"],
                project_name=row["project_name"],
                project_path=row["project_path"],
                skills=json.loads(row["skills"]),
                description=row["description"],
                request=row["request"],
                plan_text=row["plan_text"],
                subplans=json.loads(row["subplans"]),
                results=json.loads(row["results"]),
                core_memory=row["core_memory"] if "core_memory" in row.keys() else "",
                history=[dict(r) for r in hist_rows],
            )

    def save(self, project: ProjectData) -> None:
        now = datetime.now(timezone.utc).isoformat()
        _skills = list(project.skills)
        if "opalacoder" not in _skills:
            _skills = ["opalacoder"] + _skills
        with _conn(self.db_path) as conn:
            conn.execute(
                """UPDATE projects SET updated_at=?, mode=?, model=?, project_name=?, project_path=?,
                   skills=?, description=?, request=?, plan_text=?, subplans=?, results=?, core_memory=? WHERE name=?""",
                (
                    now,
                    project.mode,
                    project.model,
                    project.project_name,
                    project.project_path,
                    json.dumps(_skills, ensure_ascii=False),
                    project.description,
                    project.request,
                    project.plan_text,
                    json.dumps(project.subplans, ensure_ascii=False),
                    json.dumps(project.results, ensure_ascii=False),
                    project.core_memory,
                    project.name,
                ),
            )

    def append_message(self, project: ProjectData, role: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        message_id = None
        with _conn(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO project_history (project, timestamp, role, content) VALUES (?,?,?,?)",
                (project.name, now, role, content),
            )
            message_id = cursor.lastrowid
            
        project.history.append({"role": role, "content": content})
        
        # Envia também para o banco de dados vetorial
        try:
            from .archival import append_to_archival
            append_to_archival(
                project_name=project.name,
                message_id=str(message_id),
                role=role,
                content=content,
                timestamp=now
            )
        except Exception:
            pass


# Backward-compat alias
SessionStore = ProjectStore
