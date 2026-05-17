"""Tests for ProjectStore and ProjectData.

Verifies:
1. ProjectStore.create always includes 'opalacoder' in skills
2. ProjectStore.load round-trips all ProjectData fields correctly
3. ProjectStore.rename fails if target name already exists
4. ProjectData.context_header produces the expected format
5. ProjectStore.save persists changes and reload reflects them
6. ProjectStore.delete removes project and history
"""

import os
import tempfile
import pytest

from opalacoder.project import ProjectData, ProjectStore


@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "test.db")
    return ProjectStore(db_path=db)


def _base_args(**overrides):
    defaults = dict(
        name="myproj",
        mode="plan",
        model="fake/model",
        project_name="My Project",
        project_path="/home/user/myproject",
        skills=["python_subprocess"],
        description="A test project",
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# 1. create always adds 'opalacoder'
# ---------------------------------------------------------------------------

def test_create_always_includes_opalacoder(store):
    """Skills list must always contain 'opalacoder', even if not passed."""
    p = store.create(**_base_args(skills=["react_vite"]))
    assert "opalacoder" in p.skills


def test_create_without_skills_defaults_to_opalacoder(store):
    """When skills is None, result must still have 'opalacoder'."""
    p = store.create(**_base_args(skills=None))
    assert p.skills == ["opalacoder"]


def test_create_does_not_duplicate_opalacoder(store):
    """If opalacoder is explicitly in the list, it must not appear twice."""
    p = store.create(**_base_args(skills=["opalacoder", "html_css_js"]))
    assert p.skills.count("opalacoder") == 1


# ---------------------------------------------------------------------------
# 2. load round-trips all fields
# ---------------------------------------------------------------------------

def test_load_roundtrips_all_fields(store):
    args = _base_args()
    store.create(**args)
    loaded = store.load("myproj")

    assert loaded is not None
    assert loaded.name == "myproj"
    assert loaded.mode == "plan"
    assert loaded.model == "fake/model"
    assert loaded.project_name == "My Project"
    assert loaded.project_path == "/home/user/myproject"
    assert "opalacoder" in loaded.skills
    assert "python_subprocess" in loaded.skills
    assert loaded.description == "A test project"


def test_load_nonexistent_returns_none(store):
    assert store.load("ghost") is None


# ---------------------------------------------------------------------------
# 3. rename fails if target exists
# ---------------------------------------------------------------------------

def test_rename_fails_if_target_exists(store):
    store.create(**_base_args(name="proj_a"))
    store.create(**_base_args(name="proj_b"))
    result = store.rename("proj_a", "proj_b")
    assert result is False
    # Both should still exist under original names
    assert store.exists("proj_a")
    assert store.exists("proj_b")


def test_rename_succeeds_when_target_is_free(store):
    store.create(**_base_args(name="proj_a"))
    result = store.rename("proj_a", "proj_renamed")
    assert result is True
    assert not store.exists("proj_a")
    assert store.exists("proj_renamed")


# ---------------------------------------------------------------------------
# 4. context_header format
# ---------------------------------------------------------------------------

def test_context_header_format():
    p = ProjectData(
        name="myproj",
        project_name="My Project",
        project_path="/home/user/myproject",
    )
    header = p.context_header()
    assert header.startswith("[PROJECT:")
    assert "My Project" in header
    assert "/home/user/myproject" in header
    # Must match the format the orchestrator parses
    assert "PATH:" in header


def test_context_header_uses_name_when_project_name_empty():
    p = ProjectData(name="fallback_name", project_name="", project_path="/some/path")
    header = p.context_header()
    assert "fallback_name" in header


# ---------------------------------------------------------------------------
# 5. save persists changes
# ---------------------------------------------------------------------------

def test_save_persists_description_change(store):
    store.create(**_base_args())
    p = store.load("myproj")
    p.description = "Updated description"
    store.save(p)

    reloaded = store.load("myproj")
    assert reloaded.description == "Updated description"


def test_save_always_keeps_opalacoder_in_skills(store):
    """Even if someone accidentally removes opalacoder before save, it must be restored."""
    store.create(**_base_args())
    p = store.load("myproj")
    p.skills = ["html_css_js"]  # opalacoder removed
    store.save(p)

    reloaded = store.load("myproj")
    assert "opalacoder" in reloaded.skills


# ---------------------------------------------------------------------------
# 6. delete removes project and history
# ---------------------------------------------------------------------------

def test_delete_removes_project(store):
    store.create(**_base_args())
    assert store.exists("myproj")
    store.delete("myproj")
    assert not store.exists("myproj")
    assert store.load("myproj") is None


def test_delete_removes_history(store):
    store.create(**_base_args())
    p = store.load("myproj")
    store.append_message(p, "user", "hello")
    store.append_message(p, "assistant", "hi")

    store.delete("myproj")
    # Re-creating with same name should start with empty history
    store.create(**_base_args())
    p2 = store.load("myproj")
    assert p2.history == []


# ---------------------------------------------------------------------------
# 7. list_projects ordering
# ---------------------------------------------------------------------------

def test_list_projects_most_recent_first(store):
    store.create(**_base_args(name="old_proj"))
    store.create(**_base_args(name="new_proj"))
    projects = store.list_projects()
    names = [p["name"] for p in projects]
    # new_proj was created after old_proj, so it should appear first
    assert names.index("new_proj") < names.index("old_proj")
