#!/usr/bin/env python3
"""Level-3 script for the `html-css-js` skill: HTML/CSS/JS bug & contract detector.

Thin CLI wrapper around the existing detection logic
(opalacoder.plugins.html_css_js_tools.search_html_css_js_bugs), reused here rather
than duplicated. Prints the structured report (including any [CONTRACT ERROR] /
[SYNTAX ERROR] lines) to stdout.

Usage:
    python check_contracts.py [--path <file-or-dir>] [--project-path <dir>]

--project-path scopes the analysis to a project directory (defaults to cwd).
--path narrows the scan to a file/subdir relative to the project (defaults to ".").
"""

import argparse
import os
import sys


def _ensure_opalacoder_importable() -> None:
    try:
        import opalacoder  # noqa: F401
        return
    except Exception:
        pass
    root = os.environ.get("OPALACODER_ROOT")
    if not root:
        here = os.path.abspath(__file__)
        # scripts/ -> html-css-js/ -> skills/ -> repo root
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
    if root and root not in sys.path:
        sys.path.insert(0, root)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_contracts.py",
        description="Detect HTML/CSS/JS bugs and HTML↔JS contract mismatches.",
    )
    parser.add_argument("--path", default=".",
                        help="File or directory (relative to the project) to scan.")
    parser.add_argument("--project-path", default=None,
                        help="Project root to scope the analysis (default: cwd).")
    args = parser.parse_args(argv)

    _ensure_opalacoder_importable()

    # Scope file resolution to the project directory so get_project_path() inside
    # the detector points at the right tree.
    from opalacoder.tools import set_project_context
    from opalacoder.project import ProjectData

    project_path = os.path.abspath(args.project_path or os.getcwd())
    set_project_context(
        ProjectData(name="html-css-js", project_name="html-css-js",
                    project_path=project_path),
        None,
    )

    from opalacoder.plugins.html_css_js_tools import search_html_css_js_bugs
    fn = getattr(search_html_css_js_bugs, "_func", search_html_css_js_bugs)
    report = fn(args.path)
    print(report if report else "(no issues found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
