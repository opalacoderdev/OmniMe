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
                results         TEXT NOT NULL DEFAULT '{}',
                core_memory     TEXT NOT NULL DEFAULT '',
                alternative_model TEXT NOT NULL DEFAULT '',
                model_params    TEXT NOT NULL DEFAULT '{}'
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

        # Migração: modelo alternativo por projeto ("" → usa o ALTERNATIVE_MODEL global)
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN alternative_model TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        # Migração: model_params
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN model_params TEXT NOT NULL DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass


@dataclass
class ProjectData:
    name: str
    mode: str = "plan"
    model: str = ""
    alternative_model: str = ""   # "" → falls back to the global ALTERNATIVE_MODEL
    project_name: str = ""
    project_path: str = ""
    skills: list = field(default_factory=lambda: ["opalacoder"])
    description: str = ""
    request: str = ""
    plan_text: str = ""
    subplans: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    core_memory: str = ""
    model_params: dict = field(default_factory=lambda: {"think": True, "stream": True})
    api_key: str = ""
    api_base: str = ""
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
                "SELECT name, project_name, project_path, created_at, updated_at, mode, model, alternative_model, description, model_params FROM projects ORDER BY updated_at DESC"
            ).fetchall()
            res = []
            for r in rows:
                d = dict(r)
                if "model_params" in d and d["model_params"]:
                    try:
                        d["model_params"] = json.loads(d["model_params"])
                    except Exception:
                        d["model_params"] = {}
                else:
                    d["model_params"] = {}
                # Apply defaults for params added after project creation
                d["model_params"].setdefault("think", True)
                d["model_params"].setdefault("stream", True)
                
                # Load api_key and api_base from local .env if it exists
                d["api_key"] = ""
                d["api_base"] = ""
                proj_path = d.get("project_path")
                if proj_path and os.path.isdir(proj_path):
                    env_path = os.path.join(proj_path, ".env")
                    if os.path.isfile(env_path):
                        try:
                            with open(env_path, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if line.startswith("OPENAI_API_KEY="):
                                        d["api_key"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                                    elif line.startswith("OPENAI_API_BASE="):
                                        d["api_base"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                        except Exception:
                            pass
                
                res.append(d)
            return res

    def create(self, name: str, mode: str, model: str, project_name: str = "", project_path: str = "", skills: list = None, description: str = "", alternative_model: str = "", api_key: str = None, api_base: str = None, model_params: dict = None) -> ProjectData:
        now = datetime.now(timezone.utc).isoformat()
        _skills = skills if skills is not None else ["opalacoder"]
        if "opalacoder" not in _skills:
            _skills = ["opalacoder"] + _skills
        _model_params = model_params if model_params is not None else {}

        # Ensure the project path is absolute and exists
        abs_proj_path = os.path.abspath(project_path) if project_path else os.getcwd()
        try:
            os.makedirs(abs_proj_path, exist_ok=True)

            # 1. Initialize command-line skill inside the project's .opalacoder/skills/command-line/
            shadow_skill_dir = os.path.join(abs_proj_path, ".opalacoder", "skills", "command-line")
            os.makedirs(shadow_skill_dir, exist_ok=True)

            package_dir = os.path.dirname(os.path.abspath(__file__))
            builtin_skill_dir = os.path.join(package_dir, "skills", "command-line")
            if not os.path.isdir(builtin_skill_dir):
                repo_root = os.path.dirname(package_dir)
                builtin_skill_dir = os.path.join(repo_root, "skills", "command-line")

            if os.path.isdir(builtin_skill_dir):
                import shutil
                # Copy SKILL.md
                src_md = os.path.join(builtin_skill_dir, "SKILL.md")
                if os.path.isfile(src_md):
                    shutil.copy2(src_md, os.path.join(shadow_skill_dir, "SKILL.md"))

                # Copy scripts/command_executor.py
                src_script_dir = os.path.join(builtin_skill_dir, "scripts")
                dest_script_dir = os.path.join(shadow_skill_dir, "scripts")
                if os.path.isdir(src_script_dir):
                    os.makedirs(dest_script_dir, exist_ok=True)
                    src_executor = os.path.join(src_script_dir, "command_executor.py")
                    if os.path.isfile(src_executor):
                        shutil.copy2(src_executor, os.path.join(dest_script_dir, "command_executor.py"))

            # 2. Write project's skills.yaml containing the command-line skill
            from .skills import write_skills_yaml
            write_skills_yaml(abs_proj_path, ["command-line"])

            # 3. Write API Key and API Base to local .env if provided
            if api_key or api_base:
                env_path = os.path.join(abs_proj_path, ".env")
                env_lines = []
                if os.path.isfile(env_path):
                    try:
                        with open(env_path, "r", encoding="utf-8") as f:
                            env_lines = f.readlines()
                    except Exception:
                        pass
                
                def upsert_env(var_name, val):
                    for i, line in enumerate(env_lines):
                        if line.strip().startswith(f"{var_name}="):
                            env_lines[i] = f"{var_name}={val}\n"
                            return
                    env_lines.append(f"{var_name}={val}\n")
                    
                if api_key:
                    upsert_env("OPENAI_API_KEY", api_key)
                if api_base:
                    upsert_env("OPENAI_API_BASE", api_base)
                    
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(env_lines)

            # 4. Initialize VCS shadow git
            from .vcs import get_vcs_strategy
            from .config import get_git_strategy
            vcs = get_vcs_strategy(get_git_strategy(), abs_proj_path)
            vcs.setup()
        except (OSError, PermissionError):
            pass

        with _conn(self.db_path) as conn:
            conn.execute(
                "INSERT INTO projects (name, created_at, updated_at, mode, model, alternative_model, project_name, project_path, skills, description, core_memory, model_params) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, now, now, mode, model, alternative_model, project_name, abs_proj_path, json.dumps(_skills), description, "", json.dumps(_model_params)),
            )
        return ProjectData(name=name, mode=mode, model=model, alternative_model=alternative_model, project_name=project_name, project_path=abs_proj_path, skills=_skills, description=description, core_memory="", model_params=_model_params)

    def overwrite(self, name: str, mode: str, model: str, project_name: str = "", project_path: str = "", skills: list = None, description: str = "", alternative_model: str = "", model_params: dict = None) -> ProjectData:
        self.delete(name)
        return self.create(name, mode, model, project_name, project_path, skills, description, alternative_model, model_params=model_params)

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
            # Read api_key and api_base from local .env if it exists
            api_key = ""
            api_base = ""
            proj_path = row["project_path"]
            if proj_path and os.path.isdir(proj_path):
                env_path = os.path.join(proj_path, ".env")
                if os.path.isfile(env_path):
                    try:
                        with open(env_path, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("OPENAI_API_KEY="):
                                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                                elif line.startswith("OPENAI_API_BASE="):
                                    api_base = line.split("=", 1)[1].strip().strip('"').strip("'")
                    except Exception:
                        pass

            return ProjectData(
                name=name,
                mode=row["mode"],
                model=row["model"],
                alternative_model=row["alternative_model"] if "alternative_model" in row.keys() else "",
                project_name=row["project_name"],
                project_path=row["project_path"],
                skills=json.loads(row["skills"]),
                description=row["description"],
                request=row["request"],
                plan_text=row["plan_text"],
                subplans=json.loads(row["subplans"]),
                results=json.loads(row["results"]),
                core_memory=row["core_memory"] if "core_memory" in row.keys() else "",
                model_params={
                    "think": True, "stream": True,
                    **(json.loads(row["model_params"]) if "model_params" in row.keys() else {}),
                },
                api_key=api_key,
                api_base=api_base,
                history=[dict(r) for r in hist_rows],
            )

    def save(self, project: ProjectData) -> None:
        now = datetime.now(timezone.utc).isoformat()
        _skills = list(project.skills)
        if "opalacoder" not in _skills:
            _skills = ["opalacoder"] + _skills
        _model_params = project.model_params if hasattr(project, "model_params") else {}
        
        # Save api_key and api_base to project's local .env
        if hasattr(project, "api_key") or hasattr(project, "api_base"):
            env_path = os.path.join(project.project_path, ".env")
            env_lines = []
            if os.path.isfile(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        env_lines = f.readlines()
                except Exception:
                    pass

            def upsert_env(var_name, val):
                if val is None:
                    return
                for i, line in enumerate(env_lines):
                    if line.strip().startswith(f"{var_name}="):
                        env_lines[i] = f"{var_name}={val}\n"
                        return
                env_lines.append(f"{var_name}={val}\n")

            upsert_env("OPENAI_API_KEY", getattr(project, "api_key", ""))
            upsert_env("OPENAI_API_BASE", getattr(project, "api_base", ""))

            try:
                os.makedirs(project.project_path, exist_ok=True)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(env_lines)
            except Exception:
                pass

        with _conn(self.db_path) as conn:
            conn.execute(
                """UPDATE projects SET updated_at=?, mode=?, model=?, alternative_model=?, project_name=?, project_path=?,
                   skills=?, description=?, request=?, plan_text=?, subplans=?, results=?, core_memory=?, model_params=? WHERE name=?""",
                (
                    now,
                    project.mode,
                    project.model,
                    project.alternative_model,
                    project.project_name,
                    project.project_path,
                    json.dumps(_skills, ensure_ascii=False),
                    project.description,
                    project.request,
                    project.plan_text,
                    json.dumps(project.subplans, ensure_ascii=False),
                    json.dumps(project.results, ensure_ascii=False),
                    project.core_memory,
                    json.dumps(_model_params, ensure_ascii=False),
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
