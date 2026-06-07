"""Tests for the implement-feature Level-3 script (skills/implement-feature/scripts/run_workflow.py).

Verifies the thin CLI wrapper wiring WITHOUT invoking any LLM:
  - the script module imports and exposes its CLI
  - model resolution (default/alternative/explicit)
  - session loading falls back to a minimal ProjectData rooted at --project-path
"""

import importlib.util
import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_REPO, "skills", "skills_store", "implement-feature", "scripts", "run_workflow.py")


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_workflow_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_file_exists():
    assert os.path.isfile(_SCRIPT), "implement-feature script must exist"


def test_model_resolution():
    mod = _load_script_module()
    from opalacoder.config import DEFAULT_MODEL, ALTERNATIVE_MODEL
    assert mod._resolve_model(None) == DEFAULT_MODEL
    assert mod._resolve_model("default") == DEFAULT_MODEL
    assert mod._resolve_model("alternative") == ALTERNATIVE_MODEL
    assert mod._resolve_model("ollama/custom-x") == "ollama/custom-x"


def test_session_fallback_to_path(tmp_path):
    mod = _load_script_module()

    class Args:
        project_name = None
        project_path = str(tmp_path)
        db = None

    session, store = mod._load_session(Args())
    assert os.path.abspath(session.project_path) == os.path.abspath(str(tmp_path))
    # context_header is what the orchestrator consumes
    assert "PATH:" in session.context_header()


def test_cli_parses_required_args():
    mod = _load_script_module()
    # argparse should accept the documented invocation shape (parse only, no run)
    parser = None
    # Re-run main() parsing path by constructing argv and catching the LLM call:
    # we only assert that missing --request fails fast.
    with pytest.raises(SystemExit):
        mod.main(["--intent", "newfeat"])  # missing --request → argparse error
