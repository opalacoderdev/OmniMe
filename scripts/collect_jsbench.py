#!/usr/bin/env python3
"""
Collect JS bug-fix instances from GitHub for benchmarking OpalaCoder.

For each instance we need:
  - repo + commit before the fix (buggy state)
  - issue text (the "request" sent to OpalaCoder)
  - PR diff (reference fix)
  - test command that fails before and passes after

Usage:
    python scripts/collect_jsbench.py --out datasets/jsbench --limit 50
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def gh(endpoint: str, **kwargs) -> dict | list:
    """Call the GitHub CLI and return parsed JSON."""
    jq = kwargs.pop("jq", None)
    cmd = ["gh", "api", endpoint]
    if jq:
        cmd += ["--jq", jq]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr.strip()}")
    return json.loads(result.stdout) if not jq else result.stdout.strip()


def search_issues(page: int = 1, per_page: int = 100) -> list[dict]:
    """Search closed bug issues in JS repos that have a linked PR."""
    query = (
        "label:bug language:javascript is:issue is:closed linked:pr "
        "created:>2020-01-01 "
        "NOT react NOT next NOT vue NOT angular NOT typescript"
    )
    data = gh(
        f"search/issues?q={query.replace(' ', '+')}&per_page={per_page}&page={page}&sort=created&order=desc"
    )
    return data.get("items", [])


def get_linked_pr(owner: str, repo: str, issue_number: int) -> dict | None:
    """Find the PR that closes this issue via timeline events (uses core API, not search)."""
    try:
        events = gh(f"repos/{owner}/{repo}/issues/{issue_number}/timeline?per_page=100")
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("event") == "cross-referenced":
                src = event.get("source", {})
                issue = src.get("issue", {})
                pr_url = issue.get("pull_request", {})
                if pr_url and issue.get("state") == "closed":
                    return issue
        return None
    except Exception:
        return None


def get_pr_files(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Return files changed by a PR."""
    try:
        return gh(f"repos/{owner}/{repo}/pulls/{pr_number}/files?per_page=30")
    except Exception:
        return []


def has_test_config(owner: str, repo: str) -> bool:
    """Check if repo has jest or vitest config."""
    import base64
    try:
        raw = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/contents/package.json",
             "--jq", ".content"],
            capture_output=True, text=True
        )
        if raw.returncode != 0:
            return False
        content = raw.stdout.strip().replace("\\n", "").replace("\n", "")
        decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
        return any(kw in decoded for kw in ("jest", "vitest", "mocha", "jasmine", "ava"))
    except Exception:
        return False


def get_pr_base_commit(owner: str, repo: str, pr_number: int) -> str | None:
    """Return the base (buggy) commit SHA of a PR."""
    try:
        data = gh(f"repos/{owner}/{repo}/pulls/{pr_number}")
        return data["base"]["sha"]
    except Exception:
        return None


def is_js_only(files: list[dict]) -> bool:
    """True if all changed files are .js (no .ts, .jsx, .tsx, config files)."""
    if not files:
        return False
    for f in files:
        name = f.get("filename", "")
        if not name.endswith(".js"):
            return False
    return True


def collect(out_dir: Path, limit: int, dry_run: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    instances = []
    seen_repos: set[str] = set()
    page = 1

    print(f"Collecting up to {limit} instances into {out_dir} ...")

    while len(instances) < limit:
        try:
            issues = search_issues(page=page)
        except RuntimeError as e:
            if "1000 search results" in str(e) or "422" in str(e):
                print("GitHub search limit reached (1000 results max).")
            else:
                print(f"Search error: {e}")
            break
        if not issues:
            print("No more issues found.")
            break
        page += 1

        for issue in issues:
            if len(instances) >= limit:
                break

            repo_url = issue.get("repository_url", "")
            parts = repo_url.rstrip("/").split("/")
            owner, repo = parts[-2], parts[-1]
            issue_number = issue["number"]
            repo_full = f"{owner}/{repo}"

            # Skip repos we already have an instance from
            if repo_full in seen_repos:
                continue

            print(f"  Checking {repo_full}#{issue_number} ...", end=" ", flush=True)

            # Must have test config
            if not has_test_config(owner, repo):
                print("skip (no tests)")
                continue

            # Find linked PR
            pr = get_linked_pr(owner, repo, issue_number)
            if not pr:
                print("skip (no merged PR)")
                continue

            pr_number = pr["number"]
            files = get_pr_files(owner, repo, pr_number)

            # Only pure .js fixes (avoid framework noise)
            if not is_js_only(files):
                print(f"skip (non-js files: {[f['filename'] for f in files[:3]]})")
                continue

            # Max 3 files changed (focused fix)
            if len(files) > 3:
                print(f"skip (too many files: {len(files)})")
                continue

            base_commit = get_pr_base_commit(owner, repo, pr_number)
            if not base_commit:
                print("skip (no base commit)")
                continue

            instance = {
                "id": f"{owner}__{repo}__issue{issue_number}",
                "repo_full": repo_full,
                "clone_url": f"https://github.com/{repo_full}.git",
                "issue_number": issue_number,
                "issue_title": issue["title"],
                "issue_body": issue.get("body", "") or "",
                "issue_url": issue["html_url"],
                "pr_number": pr_number,
                "pr_url": pr["html_url"],
                "base_commit": base_commit,
                "changed_files": [f["filename"] for f in files],
                "patch": "\n".join(f.get("patch", "") for f in files),
            }

            instances.append(instance)
            seen_repos.add(repo_full)
            print(f"OK ({len(files)} file(s) changed)")

            # Save incrementally
            if not dry_run:
                inst_path = out_dir / f"{instance['id']}.json"
                inst_path.write_text(json.dumps(instance, indent=2, ensure_ascii=False))

            time.sleep(0.5)  # be polite to GitHub API

    # Save index
    index_path = out_dir / "index.json"
    index = [
        {
            "id": i["id"],
            "repo": i["repo_full"],
            "issue": i["issue_number"],
            "pr": i["pr_number"],
            "files": i["changed_files"],
        }
        for i in instances
    ]
    if not dry_run:
        index_path.write_text(json.dumps(index, indent=2))

    print(f"\nCollected {len(instances)} instances.")
    if dry_run:
        print("(dry-run: nothing written to disk)")
    else:
        print(f"Index written to {index_path}")


def main():
    parser = argparse.ArgumentParser(description="Collect JS benchmark instances from GitHub")
    parser.add_argument("--out", default="datasets/jsbench", help="Output directory")
    parser.add_argument("--limit", type=int, default=50, help="Max instances to collect")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    args = parser.parse_args()

    collect(Path(args.out), args.limit, args.dry_run)


if __name__ == "__main__":
    main()
