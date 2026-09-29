"""Reset and rederive: clear what the demo recording created, run the pipeline again from the
committed inputs in a git worktree, and prove the published figures reproduce.

Runs after the demo recording and before the tag, while the documents are written. Three parts:

1. Reset (``--reset``): delete the forecasts the site recording, the persistence check, the
   separate client verification and the replay created in the live log, by their stated notes,
   with their rows and scores, leaving the audit log alone. Needs DATABASE_URL (or
   LOOKAHEAD_RESET_DATABASE_URL) and the schema in LOOKAHEAD_DB_SCHEMA when the database is shared.
2. Rederive: in a worktree of HEAD (``--worktree``, the default) or in place, run every stage in
   the order the registry declares (``lookahead_registry.stages.assemble.ORDER``), then merge the
   manifest and render every document, with the committed manifest's as of date so the comparison
   is like for like. The worktree gets the same external data folder through a symbolic link.
3. Compare: every value and every table of the new manifest against the manifest that was on
   disk before the run. Floats may differ by one part in a billion (parallel sums); wall clock
   timings, timestamps and throughputs are reported, never judged; anything else is drift and the
   script exits non zero unless ``--allow-drift`` is passed. Then the gates run in the worktree.

    uv run python scripts/reset_and_rederive.py                          # worktree, full run
    uv run python scripts/reset_and_rederive.py --stages skill,registry  # a subset, in place
    uv run python scripts/reset_and_rederive.py --compare-only           # judge the last run
    DATABASE_URL=... uv run python scripts/reset_and_rederive.py --reset --stages none

The summary is written to results/rederive.json and the log to logs/rederive.log.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from lookahead_registry.stages.assemble import ORDER

RECORDING_NOTES = (
    "recorded session for the control room",
    "persistence check",
    "verification from a separate client",
    "replay from a separate client",
    "load test",
    "issued from the control room",
)
RELATIVE_TOLERANCE = 1e-9
STAGE_COMMANDS: dict[str, list[str]] = {
    "data": ["data"],
    "simulate": ["simulate"],
    "recovery": ["recovery"],
    "backtest_own": ["backtest", "--backend", "own"],
    "backtest_gbm": ["backtest", "--backend", "gbm"],
    "backtest_seasonal_naive": ["backtest", "--backend", "seasonal_naive"],
    "skill": ["skill"],
    "hierarchy": ["hierarchy"],
    "events": ["events"],
    "meter": ["meter"],
    "registry": ["registry"],
    "latency": ["latency"],
}
GATES = (
    "scripts/check_no_em_dash.py",
    "scripts/check_vocabulary.py",
    "scripts/check_statement.py",
    "scripts/check_published_numbers.py",
    "scripts/scan_for_planted_identifiers.py",
)
TIMING_SUFFIXES = ("_seconds", ".seconds", "_at", "per_minute", "_ms")


def log(handle: Any, message: str) -> None:
    line = f"{datetime.now(UTC).strftime('%H:%M:%S')} {message}"
    print(line, flush=True)
    handle.write(line + "\n")
    handle.flush()


def reset_log(url: str, schema: str, handle: Any) -> dict[str, int]:
    """Delete the forecasts the recording and the checks created, with their rows and scores."""
    import psycopg

    plain = url.replace("postgresql+psycopg://", "postgresql://")
    prefix = f"{schema}." if schema else ""
    counts = {"scores": 0, "rows": 0, "forecasts": 0}
    with psycopg.connect(plain) as conn, conn.cursor() as cur:
        cur.execute(
            f"delete from {prefix}scores where forecast_id in (select forecast_id from {prefix}forecasts where note = any(%s))",
            (list(RECORDING_NOTES),),
        )
        counts["scores"] = cur.rowcount
        cur.execute(
            f"delete from {prefix}forecast_rows where forecast_id in (select forecast_id from {prefix}forecasts where note = any(%s))",
            (list(RECORDING_NOTES),),
        )
        counts["rows"] = cur.rowcount
        cur.execute(f"delete from {prefix}forecasts where note = any(%s)", (list(RECORDING_NOTES),))
        counts["forecasts"] = cur.rowcount
        conn.commit()
    log(handle, f"reset: removed {counts}; the audit log is left alone")
    return counts


def run_stage(name: str, cwd: Path, env: dict[str, str], handle: Any) -> float:
    started = time.time()
    command = ["uv", "run", "lookahead", *STAGE_COMMANDS[name]]
    log(handle, "run " + " ".join(command) + f" in {cwd}")
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    handle.write(result.stdout)
    handle.write(result.stderr)
    if result.returncode != 0:
        log(handle, f"stage {name} failed with exit code {result.returncode}")
        print(result.stdout[-4000:])
        print(result.stderr[-4000:])
        raise SystemExit(f"stage {name} failed")
    seconds = time.time() - started
    log(handle, f"stage {name} finished in {seconds:,.0f} seconds")
    return seconds


def run_python(script: list[str], cwd: Path, env: dict[str, str], handle: Any) -> bool:
    command = ["uv", "run", "python", *script]
    log(handle, "run " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    handle.write(result.stdout)
    handle.write(result.stderr)
    if result.returncode != 0:
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
    return result.returncode == 0


def _same_scalar(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a == b)
    if isinstance(a, int | float) and isinstance(b, int | float):
        if isinstance(a, float) and isinstance(b, float) and (math.isnan(a) and math.isnan(b)):
            return True
        return math.isclose(float(a), float(b), rel_tol=RELATIVE_TOLERANCE, abs_tol=1e-12)
    return bool(a == b)


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Every difference between two manifests, as one line each. Wall clock timings, timestamps
    and throughputs are reported by ``timing_differences`` instead; when a stage ran is not a claim."""
    drift: list[str] = []
    for bucket in ("values", "tables"):
        old = before.get(bucket, {})
        new = after.get(bucket, {})
        for key in sorted(set(old) | set(new)):
            if key not in new:
                drift.append(f"{bucket} {key}: missing after the rederive")
                continue
            if key not in old:
                drift.append(f"{bucket} {key}: new since the committed manifest")
                continue
            if bucket == "values":
                if key.endswith(TIMING_SUFFIXES):
                    continue
                if not _same_scalar(old[key]["value"], new[key]["value"]):
                    drift.append(f"value {key}: {old[key]['value']!r} became {new[key]['value']!r}")
            else:
                rows_old, rows_new = old[key]["rows"], new[key]["rows"]
                if len(rows_old) != len(rows_new) or old[key]["columns"] != new[key]["columns"]:
                    drift.append(f"table {key}: shape changed")
                    continue
                for i, (ro, rn) in enumerate(zip(rows_old, rows_new, strict=True)):
                    for j, (a, b) in enumerate(zip(ro, rn, strict=True)):
                        if not _same_scalar(a, b):
                            drift.append(f"table {key} row {i} col {j}: {a!r} became {b!r}")
    return drift


def timing_differences(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for key, entry in after.get("values", {}).items():
        if key.endswith(TIMING_SUFFIXES) and key in before.get("values", {}):
            out[key] = [before["values"][key]["value"], entry["value"]]
    return out


def make_worktree(handle: Any) -> Path:
    """A worktree of HEAD beside the repository, with the external data linked in."""
    target = ROOT.parent / f"{ROOT.name}-rederive"
    if target.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(target)], cwd=ROOT, check=False)
        shutil.rmtree(target, ignore_errors=True)
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT, check=False)
    subprocess.run(["git", "worktree", "add", "--detach", str(target), "HEAD"], cwd=ROOT, check=True)
    external = ROOT / "data" / "external"
    if external.exists():
        link = target / "data" / "external"
        if link.exists() or link.is_symlink():
            shutil.rmtree(link, ignore_errors=True)
        link.symlink_to(external, target_is_directory=True)
    # The frames the repository does not carry are copied in, so stages that read them can run.
    for rel in (
        "results/backtest",
        "results/hierarchy",
        "results/models",
        "results/latency",
        "results/deploy",
        "results/live_check.json",
    ):
        src = ROOT / rel
        dst = target / rel
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    subprocess.run(["uv", "sync", "--frozen"], cwd=target, check=True, capture_output=True)
    log(
        handle,
        f"worktree at {target} ({subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=target, capture_output=True, text=True).stdout.strip()})",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stages", default="all", help="comma separated stage names, 'all' or 'none'")
    parser.add_argument(
        "--as-of", default=None, help="override the as of date (default: the committed manifest's)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="delete the recording's rows from the live log first"
    )
    parser.add_argument(
        "--compare-only", action="store_true", help="only compare the last run's manifest with the snapshot"
    )
    parser.add_argument(
        "--in-place", action="store_true", help="run in this checkout rather than in a worktree"
    )
    parser.add_argument("--allow-drift", action="store_true")
    parser.add_argument("--skip-gates", action="store_true")
    parser.add_argument("--workers", type=int, default=2, help="worker processes for the recovery study")
    args = parser.parse_args()

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    manifest_path = ROOT / "results" / "manifest.json"
    snapshot_path = ROOT / "results" / "manifest.before-rederive.json"
    summary_path = ROOT / "results" / "rederive.json"
    with (logs / "rederive.log").open("a", encoding="utf-8") as handle:
        log(handle, "reset and rederive started")
        summary: dict[str, Any] = {
            "started_at": datetime.now(UTC).isoformat(),
            "stages": {},
            "reset": None,
            "where": "in place",
        }

        if args.reset:
            url = os.environ.get("LOOKAHEAD_RESET_DATABASE_URL") or os.environ.get("DATABASE_URL")
            if not url:
                raise SystemExit("--reset needs DATABASE_URL or LOOKAHEAD_RESET_DATABASE_URL")
            summary["reset"] = reset_log(url, os.environ.get("LOOKAHEAD_DB_SCHEMA", ""), handle)

        after_path = manifest_path
        if not args.compare_only:
            if not manifest_path.exists():
                raise SystemExit("results/manifest.json is missing; there is nothing to compare against")
            shutil.copyfile(manifest_path, snapshot_path)
            before = json.loads(snapshot_path.read_text(encoding="utf-8"))
            env = {**os.environ, "LOOKAHEAD_AS_OF": args.as_of or str(before["as_of"])}
            stages = (
                list(ORDER)
                if args.stages == "all"
                else []
                if args.stages == "none"
                else args.stages.split(",")
            )
            unknown = [s for s in stages if s not in STAGE_COMMANDS]
            if unknown:
                raise SystemExit(f"unknown stages: {unknown}; choose from {list(STAGE_COMMANDS)}")
            cwd = ROOT
            if stages and not args.in_place:
                cwd = make_worktree(handle)
                summary["where"] = str(cwd)
                summary["commit"] = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True
                ).stdout.strip()
            if "recovery" in stages:
                STAGE_COMMANDS["recovery"] = ["recovery", "--workers", str(args.workers)]
            for name in stages:
                summary["stages"][name] = run_stage(name, cwd, env, handle)
            if stages:
                started = time.time()
                for command in (["uv", "run", "lookahead", "manifest"], ["uv", "run", "lookahead", "marts"]):
                    log(handle, "run " + " ".join(command))
                    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
                    handle.write(result.stdout + result.stderr)
                    if result.returncode != 0:
                        print(result.stderr[-3000:])
                        raise SystemExit("merging the manifest or writing the marts failed")
                if not run_python(["scripts/check_published_numbers.py", "--write"], cwd, env, handle):
                    raise SystemExit("rendering the documents failed")
                summary["stages"]["manifest_render_marts"] = time.time() - started
            after_path = cwd / "results" / "manifest.json"
        else:
            if not snapshot_path.exists():
                raise SystemExit("no snapshot to compare against; run without --compare-only first")
            before = json.loads(snapshot_path.read_text(encoding="utf-8"))
            candidate = ROOT.parent / f"{ROOT.name}-rederive" / "results" / "manifest.json"
            if candidate.exists():
                after_path = candidate
            cwd = after_path.parents[1]

        after = json.loads(after_path.read_text(encoding="utf-8"))
        drift = compare(before, after)
        summary["values_compared"] = len(after.get("values", {}))
        summary["tables_compared"] = len(after.get("tables", {}))
        summary["drift"] = drift
        summary["timing_differences"] = timing_differences(before, after)
        for line in drift[:200]:
            log(handle, "drift: " + line)
        log(
            handle,
            f"compared {summary['values_compared']} values and {summary['tables_compared']} tables; {len(drift)} drifted",
        )

        gates_ok = True
        if not args.skip_gates:
            for gate in GATES:
                ok = run_python([gate], cwd, dict(os.environ), handle)
                log(handle, f"gate {gate}: {'passed' if ok else 'FAILED'}")
                gates_ok = gates_ok and ok
        summary["gates_passed"] = gates_ok
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["reproduced"] = not drift and gates_ok
        summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        log(handle, f"summary written to {summary_path.relative_to(ROOT)}")
        if drift and not args.allow_drift:
            print(f"{len(drift)} published figures did not reproduce; see logs/rederive.log")
            return 1
        if not gates_ok:
            return 1
        print("every published figure reproduced and every gate passed" if not drift else "drift allowed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
