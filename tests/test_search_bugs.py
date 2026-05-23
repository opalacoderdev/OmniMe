"""Tests for search_bugs() — three-layer bug detection tool."""

import textwrap
import os
import pytest
from opalacoder.tools import (
    search_bugs,
    set_project_context,
    _layer_ast,
    _layer_linters,
    _collect_python_files,
    BugReport,
)

# @as_tool wraps the function in a FunctionBlock; access the original via ._func
_search_bugs = search_bugs._func


class _FakeSession:
    def __init__(self, path: str):
        self.project_path = path
        self.core_memory = ""
        self.name = "test"


@pytest.fixture()
def project_dir(tmp_path):
    session = _FakeSession(str(tmp_path))
    set_project_context(session)
    return tmp_path


def _write(tmp_path, name: str, code: str) -> str:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return str(p)


# ---------------------------------------------------------------------------
# _collect_python_files
# ---------------------------------------------------------------------------

def test_collect_skips_non_py(project_dir):
    (project_dir / "script.py").write_text("x = 1")
    (project_dir / "readme.md").write_text("# readme")
    files = _collect_python_files(str(project_dir), ".")
    assert all(f.endswith(".py") for f in files)
    assert len(files) == 1


def test_collect_single_file(project_dir):
    p = _write(project_dir, "only.py", "x = 1")
    files = _collect_python_files(str(project_dir), "only.py")
    assert files == [str(project_dir / "only.py")]


def test_collect_no_py_returns_empty(project_dir):
    (project_dir / "readme.md").write_text("# readme")
    files = _collect_python_files(str(project_dir), ".")
    assert files == []


# ---------------------------------------------------------------------------
# Layer 2: AST checks
# ---------------------------------------------------------------------------

def test_ast_bare_except(project_dir):
    _write(project_dir, "a.py", """\
        try:
            pass
        except:
            pass
    """)
    bugs = _layer_ast([str(project_dir / "a.py")], str(project_dir))
    rules = [b.rule for b in bugs]
    assert "ast:bare-except" in rules


def test_ast_mutable_default(project_dir):
    _write(project_dir, "b.py", """\
        def foo(x=[]):
            return x
    """)
    bugs = _layer_ast([str(project_dir / "b.py")], str(project_dir))
    rules = [b.rule for b in bugs]
    assert "ast:mutable-default-arg" in rules


def test_ast_except_pass(project_dir):
    _write(project_dir, "c.py", """\
        try:
            x = 1
        except ValueError:
            pass
    """)
    bugs = _layer_ast([str(project_dir / "c.py")], str(project_dir))
    rules = [b.rule for b in bugs]
    assert "ast:except-pass" in rules


def test_ast_none_equality(project_dir):
    _write(project_dir, "d.py", """\
        x = None
        if x == None:
            pass
    """)
    bugs = _layer_ast([str(project_dir / "d.py")], str(project_dir))
    rules = [b.rule for b in bugs]
    assert "ast:comparison-with-none" in rules


def test_ast_shadowed_builtin_function(project_dir):
    _write(project_dir, "e.py", """\
        def list(x):
            return x
    """)
    bugs = _layer_ast([str(project_dir / "e.py")], str(project_dir))
    rules = [b.rule for b in bugs]
    assert "ast:shadowed-builtin" in rules


def test_ast_shadowed_builtin_variable(project_dir):
    _write(project_dir, "f.py", """\
        len = 10
    """)
    bugs = _layer_ast([str(project_dir / "f.py")], str(project_dir))
    rules = [b.rule for b in bugs]
    assert "ast:shadowed-builtin" in rules


def test_ast_syntax_error(project_dir):
    (project_dir / "bad.py").write_text("def foo(:\n    pass\n")
    bugs = _layer_ast([str(project_dir / "bad.py")], str(project_dir))
    assert any(b.rule == "ast:syntax-error" and b.severity == "error" for b in bugs)


def test_ast_clean_file_no_bugs(project_dir):
    _write(project_dir, "clean.py", """\
        def add(a: int, b: int) -> int:
            return a + b
    """)
    bugs = _layer_ast([str(project_dir / "clean.py")], str(project_dir))
    assert bugs == []


# ---------------------------------------------------------------------------
# Layer 1: pyflakes (installed as test dependency)
# ---------------------------------------------------------------------------

def test_linter_undefined_name(project_dir):
    _write(project_dir, "undef.py", """\
        print(undefined_variable)
    """)
    bugs = _layer_linters([str(project_dir / "undef.py")], str(project_dir))
    assert any(b.rule == "pyflakes" for b in bugs), "pyflakes should detect undefined name"


def test_linter_unused_import(project_dir):
    _write(project_dir, "unused.py", """\
        import os
        x = 1
    """)
    bugs = _layer_linters([str(project_dir / "unused.py")], str(project_dir))
    assert any(b.rule == "pyflakes" for b in bugs)


# ---------------------------------------------------------------------------
# search_bugs() integration
# ---------------------------------------------------------------------------

def test_search_bugs_returns_string(project_dir):
    _write(project_dir, "x.py", "x = 1")
    result = _search_bugs(path=".", llm_check=False)
    assert isinstance(result, str)


def test_search_bugs_no_python_files(project_dir):
    result = _search_bugs(path=".", llm_check=False)
    assert "No Python files found" in result


def test_search_bugs_detects_mutable_default(project_dir):
    _write(project_dir, "bug.py", """\
        def foo(x=[]):
            return x
    """)
    result = _search_bugs(path=".", llm_check=False)
    assert "mutable" in result.lower() or "ast:mutable" in result


def test_search_bugs_deduplicates(project_dir):
    _write(project_dir, "dup.py", """\
        try:
            pass
        except:
            pass
    """)
    result = _search_bugs(path=".", llm_check=False)
    count = result.count("ast:bare-except")
    assert count == 1, "same bug should not appear twice"


def test_search_bugs_errors_before_warnings(project_dir):
    _write(project_dir, "mixed.py", """\
        def foo(x=[]):
            try:
                pass
            except:
                pass
    """)
    result = _search_bugs(path=".", llm_check=False)
    lines = [l for l in result.splitlines() if l.startswith("[")]
    severities = [l.split("]")[0].lstrip("[") for l in lines]
    # All ERRORs must appear before WARNINGs
    first_warning = next((i for i, s in enumerate(severities) if s == "WARNING"), len(severities))
    last_error = next((len(severities) - 1 - i for i, s in enumerate(reversed(severities)) if s == "ERROR"), -1)
    assert last_error < first_warning or first_warning == len(severities)


def test_search_bugs_single_file(project_dir):
    _write(project_dir, "ok.py", "x = 1")
    _write(project_dir, "bug.py", "def foo(x={}): pass")
    result = _search_bugs(path="bug.py", llm_check=False)
    assert "bug.py" in result
    assert "ok.py" not in result


def test_bug_report_to_dict():
    b = BugReport(file="a.py", line=10, column=5, severity="error",
                  message="test", rule="ast:test", source="ast")
    d = b.to_dict()
    assert d["file"] == "a.py"
    assert d["line"] == 10
    assert d["severity"] == "error"
    assert d["source"] == "ast"
