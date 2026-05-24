"""Default language-agnostic H2 reviewer.

Checks whether the worker actually changed any of the related files on disk.
Uses the shadow-git diff to detect changes — no language-specific logic.

Signature required by load_skill_reviewers:
    def reviewer(project_path: str, task_goal: str, related_files: list[str]) -> dict
    returns {"done": bool, "summary": str, "corrections": list[str]}
"""

from pathlib import Path


def default_reviewer(project_path: str, task_goal: str, related_files: list[str]) -> dict:
    """Accept the task if any related file changed on disk; reject if nothing changed.

    This is the fallback reviewer used when a skill has no custom reviewer declared.
    It relies on the shadow-git diff: if no files changed since the last checkpoint,
    the worker almost certainly did not apply the required edit.

    Conservative by design: when shadow git is unavailable or there is insufficient
    information to reject, return done=True so the LLM reviewer makes the final call.
    """
    changed: list[str] = []
    git_available = False
    try:
        from opalacoder.vcs import _run_shadow_git
        res = _run_shadow_git("status --porcelain")
        if res.returncode == 0:
            git_available = True
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    fname = parts[1].strip()
                    if " -> " in fname:
                        fname = fname.split(" -> ", 1)[1]
                    changed.append(fname.strip())
    except Exception:
        pass

    # Without shadow git we can't tell what changed — defer to LLM reviewer entirely
    if not git_available:
        return {
            "done": True,
            "summary": "Default reviewer: shadow git unavailable — deferring to LLM reviewer.",
            "corrections": [],
        }

    # Shadow git is available — use the diff as the authoritative source
    if not changed:
        # Nothing changed at all — only reject if there were related_files to edit
        # (a read-only task or analysis task legitimately changes no files)
        if related_files:
            return {
                "done": False,
                "summary": "Default reviewer: no files changed on disk since last checkpoint.",
                "corrections": [
                    "Read the target file first, then apply the edit using edit_file "
                    "with old_str copied verbatim from the file."
                ],
            }
        # No related_files and no changes — defer to LLM reviewer
        return {
            "done": True,
            "summary": "Default reviewer: no files expected to change — deferring to LLM reviewer.",
            "corrections": [],
        }

    return {
        "done": True,
        "summary": f"Default reviewer: {len(changed)} file(s) changed on disk — task accepted.",
        "corrections": [],
    }
