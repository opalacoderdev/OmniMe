#!/usr/bin/env python3
"""
Evaluate OpalaCoder against the JS benchmark dataset.

For each instance:
  1. Clone the repo at base_commit (buggy state) into a temp dir
  2. Send issue_title + issue_body as request to OpalaCoder
  3. Run `npm test` and record pass/fail
  4. Write results to datasets/jsbench_results.json

Usage:
    python scripts/eval_jsbench.py [--ids ID1 ID2 ...] [--limit N] [--out FILE]
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Make sure we run from project root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from opalacoder.config import DEFAULT_MODEL
from opalacoder.session import ProjectStore
from opalacoder.project import ProjectData


DATASET_DIR = ROOT / "datasets" / "jsbench"
DEFAULT_OUT = ROOT / "datasets" / "jsbench_results.json"
MAX_RETRIES = 2
NPM_TEST_TIMEOUT = 120  # seconds


def load_instances(ids: list[str] | None, limit: int) -> list[dict]:
    index = json.loads((DATASET_DIR / "index.json").read_text())
    instances = []
    for entry in index:
        if ids and entry["id"] not in ids:
            continue
        inst_path = DATASET_DIR / f"{entry['id']}.json"
        if inst_path.exists():
            instances.append(json.loads(inst_path.read_text()))
    if limit:
        instances = instances[:limit]
    return instances


def clone_at_commit(clone_url: str, base_commit: str, target_dir: Path) -> bool:
    """Clone repo and checkout the buggy base commit."""
    try:
        subprocess.run(
            ["git", "clone", "--quiet", clone_url, str(target_dir)],
            check=True, capture_output=True, timeout=120
        )
        subprocess.run(
            ["git", "checkout", base_commit],
            cwd=target_dir, check=True, capture_output=True, timeout=30
        )
        return True
    except Exception as e:
        print(f"    Clone failed: {e}", flush=True)
        return False


def npm_install(project_dir: Path) -> bool:
    try:
        subprocess.run(
            ["npm", "install", "--silent", "--no-audit", "--no-fund"],
            cwd=project_dir, check=True, capture_output=True,
            timeout=180
        )
        return True
    except Exception as e:
        print(f"    npm install failed: {e}", flush=True)
        return False


def run_tests(project_dir: Path) -> tuple[bool, str]:
    """Run npm test, return (passed, output)."""
    try:
        result = subprocess.run(
            ["npm", "test", "--", "--passWithNoTests"],
            cwd=project_dir, capture_output=True, text=True,
            timeout=NPM_TEST_TIMEOUT
        )
        output = (result.stdout + result.stderr)[-3000:]
        passed = result.returncode == 0
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


async def run_opalacoder(project_dir: Path, request: str, model: str) -> str:
    """Run OpalaCoder pipeline on the project with the given request."""
    import unittest.mock as mock
    from opalacoder.cli import run_pipeline
    import opalacoder.tools as _tools_mod

    db_dir = project_dir / ".opalacoder"
    db_dir.mkdir(exist_ok=True)
    store = ProjectStore(db_path=str(db_dir / "eval.db"))
    project = ProjectData(
        name="eval",
        project_path=str(project_dir),
        project_name="eval",
        model=model,
    )
    store.save(project)

    with mock.patch("opalacoder.cli.T") as _t, \
         mock.patch("opalacoder.workflow_orchestrator.T") as _wt, \
         mock.patch("opalacoder.planner.T") as _pt:
        for m in (_t, _wt, _pt):
            m.ask = mock.MagicMock(return_value="")
            m.show_plan = mock.MagicMock()
            m.section = mock.MagicMock()
            m.success = mock.MagicMock()
            m.info = mock.MagicMock()
            m.warning = mock.MagicMock()
            m.thinking = mock.MagicMock()
            m.error = mock.MagicMock()
            m.console = mock.MagicMock()
            m.spinner = mock.MagicMock()
            m.spinner.return_value.__enter__ = mock.MagicMock(return_value=None)
            m.spinner.return_value.__exit__ = mock.MagicMock(return_value=False)

        # Pin project path so tools write to the right directory
        with mock.patch.object(_tools_mod, "get_project_path", return_value=str(project_dir)):
            try:
                result = await run_pipeline(
                    project=project,
                    store=store,
                    max_retries=MAX_RETRIES,
                    request=request,
                    active_model=model,
                )
                return result or "(no result)"
            except Exception as e:
                return f"ERROR: {e}"


async def evaluate_instance(instance: dict, model: str, tmp_root: Path) -> dict:
    inst_id = instance["id"]
    print(f"\n[{inst_id}]", flush=True)

    work_dir = tmp_root / inst_id
    work_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "id": inst_id,
        "repo": instance["repo_full"],
        "issue": instance["issue_number"],
        "status": "unknown",
        "tests_before": None,
        "tests_after": None,
        "opalacoder_result": "",
        "elapsed_s": 0,
    }

    # 1. Clone at buggy commit
    print("  Cloning...", flush=True)
    if not clone_at_commit(instance["clone_url"], instance["base_commit"], work_dir):
        result["status"] = "clone_failed"
        return result

    # 2. npm install
    print("  Installing dependencies...", flush=True)
    if not npm_install(work_dir):
        result["status"] = "install_failed"
        return result

    # 3. Run tests before (should fail or be broken)
    print("  Running tests BEFORE fix...", flush=True)
    before_passed, before_out = run_tests(work_dir)
    result["tests_before"] = {"passed": before_passed, "output": before_out}
    print(f"    Before: {'PASS' if before_passed else 'FAIL'}", flush=True)

    # 4. Build request from issue
    request = f"{instance['issue_title']}\n\n{instance['issue_body']}".strip()
    print(f"  Running OpalaCoder (model={model})...", flush=True)

    t0 = time.monotonic()
    oc_result = await run_opalacoder(work_dir, request, model)
    result["elapsed_s"] = round(time.monotonic() - t0, 1)
    result["opalacoder_result"] = oc_result[:500]
    print(f"  OpalaCoder done in {result['elapsed_s']}s", flush=True)

    # 5. Run tests after
    print("  Running tests AFTER fix...", flush=True)
    after_passed, after_out = run_tests(work_dir)
    result["tests_after"] = {"passed": after_passed, "output": after_out}
    print(f"    After:  {'PASS' if after_passed else 'FAIL'}", flush=True)

    # 6. Determine outcome
    if not before_passed and after_passed:
        result["status"] = "fixed"
    elif before_passed and after_passed:
        result["status"] = "already_passing"
    elif before_passed and not after_passed:
        result["status"] = "regression"
    else:
        result["status"] = "not_fixed"

    print(f"  → {result['status']}", flush=True)
    return result


async def main_async(args):
    model = DEFAULT_MODEL
    print(f"Model: {model}")

    instances = load_instances(args.ids, args.limit)
    print(f"Evaluating {len(instances)} instance(s)...\n")

    out_path = Path(args.out)
    # Load existing results to allow resuming
    existing: dict[str, dict] = {}
    if out_path.exists():
        for r in json.loads(out_path.read_text()):
            existing[r["id"]] = r

    results = list(existing.values())

    with tempfile.TemporaryDirectory(prefix="opalabench_") as tmp_root:
        for instance in instances:
            if instance["id"] in existing:
                print(f"[{instance['id']}] already evaluated, skipping.")
                continue
            r = await evaluate_instance(instance, model, Path(tmp_root))
            results.append(r)
            out_path.write_text(json.dumps(results, indent=2))

    # Print summary
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    total = len(results)
    fixed = counts.get("fixed", 0)
    print(f"\n{'='*50}")
    print(f"Results: {total} instances")
    for status, n in sorted(counts.items()):
        print(f"  {status:20s}: {n}")
    if total > 0:
        print(f"\n  Fix rate: {fixed}/{total} = {fixed/total*100:.1f}%")
    print(f"{'='*50}")
    print(f"Full results: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate OpalaCoder on JS benchmark")
    parser.add_argument("--ids", nargs="*", help="Specific instance IDs to evaluate")
    parser.add_argument("--limit", type=int, default=0, help="Max instances (0=all)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Results output file")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
