"""Tests for the skills loading and filtering system.

Verifies:
1. load_project_skills always includes 'abcode' regardless of input list
2. _filter_by_scope returns only skills matching the target scope
3. find_skill_file respects priority order: project > repo > global
4. Skill frontmatter is parsed correctly (tags, description, scope, content)
5. Skills with scope='orchestrator' are excluded from the classifier
6. Skills with scope='classifier' are excluded from the orchestrator
"""

import os
import tempfile
import textwrap
import pytest

from abcode.skills import (
    load_project_skills,
    load_skills,
    find_skill_file,
    _filter_by_scope,
    _parse_skill_file,
    _skill_search_dirs,
    SCOPE_ALL,
    SCOPE_ORCHESTRATOR,
    SCOPE_CLASSIFIER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_skill(directory: str, name: str, content: str) -> str:
    """Write a skill .md file and return its path."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.md")
    with open(path, "w") as f:
        f.write(textwrap.dedent(content))
    return path


# ---------------------------------------------------------------------------
# 1. load_project_skills always includes 'abcode'
# ---------------------------------------------------------------------------

def test_load_project_skills_always_adds_abcode(tmp_path):
    """abcode must always be present, even if not in the requested skill list."""
    skills_dir = str(tmp_path / "skills")
    _write_skill(skills_dir, "abcode", """\
        tags: abcode
        description: Core ABCode skill.
        scope: all
        ---
        Core instructions.
    """)
    _write_skill(skills_dir, "react_vite", """\
        tags: react, vite
        description: React/Vite skill.
        scope: orchestrator
        ---
        Use npx -y create-vite.
    """)

    result = load_project_skills(str(tmp_path), skill_names=["react_vite"])
    names = [s["name"] for s in result]
    assert "abcode" in names


def test_load_project_skills_empty_list_still_has_abcode(tmp_path):
    """Even with an empty skills list, abcode must be loaded."""
    skills_dir = str(tmp_path / "skills")
    _write_skill(skills_dir, "abcode", """\
        tags: abcode
        description: Core.
        scope: all
        ---
        Core.
    """)

    result = load_project_skills(str(tmp_path), skill_names=[])
    names = [s["name"] for s in result]
    assert "abcode" in names


# ---------------------------------------------------------------------------
# 2. _filter_by_scope
# ---------------------------------------------------------------------------

def _make_skill(name: str, scope: str) -> dict:
    return {"name": name, "description": "", "tags": [], "scope": scope, "content": ""}


def test_filter_classifier_excludes_orchestrator_only():
    skills = [
        _make_skill("s_all", SCOPE_ALL),
        _make_skill("s_orch", SCOPE_ORCHESTRATOR),
        _make_skill("s_class", SCOPE_CLASSIFIER),
    ]
    result = _filter_by_scope(skills, SCOPE_CLASSIFIER)
    names = [s["name"] for s in result]
    assert "s_all" in names
    assert "s_class" in names
    assert "s_orch" not in names


def test_filter_orchestrator_excludes_classifier_only():
    skills = [
        _make_skill("s_all", SCOPE_ALL),
        _make_skill("s_orch", SCOPE_ORCHESTRATOR),
        _make_skill("s_class", SCOPE_CLASSIFIER),
    ]
    result = _filter_by_scope(skills, SCOPE_ORCHESTRATOR)
    names = [s["name"] for s in result]
    assert "s_all" in names
    assert "s_orch" in names
    assert "s_class" not in names


# ---------------------------------------------------------------------------
# 3. find_skill_file priority order
# ---------------------------------------------------------------------------

def test_find_skill_file_prefers_project_local(tmp_path, monkeypatch):
    """A skill in the project's skills/ dir must shadow the repo-level skill."""
    # Repo root skill
    repo_root = tmp_path / "repo"
    repo_skills = repo_root / "skills"
    _write_skill(str(repo_skills), "myskill", "tags: x\ndescription: repo version.\n---\nRepo content.")

    # Project-local skill
    project_dir = tmp_path / "project"
    project_skills = project_dir / "skills"
    _write_skill(str(project_skills), "myskill", "tags: x\ndescription: project version.\n---\nProject content.")

    # Monkeypatch _skill_search_dirs to use our tmp dirs
    def fake_dirs(project_path=""):
        dirs = []
        if project_path:
            dirs.append(os.path.join(project_path, "skills"))
        dirs.append(str(repo_skills))
        return dirs

    monkeypatch.setattr("abcode.skills._skill_search_dirs", fake_dirs)

    found = find_skill_file("myskill", project_path=str(project_dir))
    assert found is not None
    assert str(project_skills) in found


# ---------------------------------------------------------------------------
# 4. Frontmatter parsing
# ---------------------------------------------------------------------------

def test_parse_skill_file_extracts_all_fields(tmp_path):
    path = _write_skill(str(tmp_path), "test_skill", """\
        tags: python, flask, web
        description: Flask web development skill.
        scope: orchestrator
        ---
        Use Flask for web apps.
        Remember to use app.run(debug=False).
    """)

    skill = _parse_skill_file(path)
    assert skill is not None
    assert skill["name"] == "test_skill"
    assert "python" in skill["tags"]
    assert "flask" in skill["tags"]
    assert skill["description"] == "Flask web development skill."
    assert skill["scope"] == SCOPE_ORCHESTRATOR
    assert "Flask" in skill["content"]
    # Frontmatter lines must not appear in content
    assert "tags:" not in skill["content"]
    assert "description:" not in skill["content"]
    assert "scope:" not in skill["content"]


def test_parse_skill_file_defaults_scope_to_all(tmp_path):
    """A skill without a scope field must default to 'all'."""
    path = _write_skill(str(tmp_path), "noscope", """\
        tags: test
        description: No scope defined.
        ---
        Some content.
    """)

    skill = _parse_skill_file(path)
    assert skill["scope"] == SCOPE_ALL


def test_parse_skill_file_returns_none_for_missing_file(tmp_path):
    result = _parse_skill_file(str(tmp_path / "nonexistent.md"))
    assert result is None


# ---------------------------------------------------------------------------
# 5 & 6. Scope enforcement via load_project_skills + _filter_by_scope
# ---------------------------------------------------------------------------

def test_orchestrator_scope_skill_not_injected_into_classifier(tmp_path):
    """A skill with scope=orchestrator must not appear in classifier-scoped output."""
    skills_dir = str(tmp_path / "skills")
    _write_skill(skills_dir, "abcode", "tags: abcode\ndescription: Core.\nscope: all\n---\nCore.")
    _write_skill(skills_dir, "orch_only", "tags: build\ndescription: Orch only.\nscope: orchestrator\n---\nBuild stuff.")

    all_loaded = load_project_skills(str(tmp_path), skill_names=["abcode", "orch_only"])
    classifier_skills = _filter_by_scope(all_loaded, SCOPE_CLASSIFIER)
    names = [s["name"] for s in classifier_skills]

    assert "abcode" in names
    assert "orch_only" not in names


def test_classifier_scope_skill_not_injected_into_orchestrator(tmp_path):
    """A skill with scope=classifier must not appear in orchestrator-scoped output."""
    skills_dir = str(tmp_path / "skills")
    _write_skill(skills_dir, "abcode", "tags: abcode\ndescription: Core.\nscope: all\n---\nCore.")
    _write_skill(skills_dir, "class_only", "tags: help\ndescription: Classifier only.\nscope: classifier\n---\nHelp text.")

    all_loaded = load_project_skills(str(tmp_path), skill_names=["abcode", "class_only"])
    orchestrator_skills = _filter_by_scope(all_loaded, SCOPE_ORCHESTRATOR)
    names = [s["name"] for s in orchestrator_skills]

    assert "abcode" in names
    assert "class_only" not in names
