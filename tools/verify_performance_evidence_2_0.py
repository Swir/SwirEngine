from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "performance_evidence_2_0.json"
DOC_PATH = ROOT / "docs" / "PERFORMANCE_EVIDENCE_2_0.md"
MAX_WORKLOADS = 16
MAX_OUTPUT_CHARS = 16_384
TIMEOUT_SECONDS = 45.0


def _load_contract() -> dict[str, Any]:
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise RuntimeError("unsupported performance evidence schema")
    workloads = data.get("workloads")
    if not isinstance(workloads, list) or not workloads or len(workloads) > MAX_WORKLOADS:
        raise RuntimeError("performance workload inventory must be non-empty and bounded")
    ids: set[str] = set()
    for workload in workloads:
        if not isinstance(workload, dict):
            raise RuntimeError("performance workload entries must be objects")
        workload_id = str(workload.get("id", "")).strip()
        if not workload_id or workload_id in ids:
            raise RuntimeError("performance workload ids must be non-empty and unique")
        ids.add(workload_id)
        command = str(workload.get("command", "")).strip()
        marker = str(workload.get("expected_marker", "")).strip()
        threshold = str(workload.get("threshold_source", "")).strip()
        if not command.startswith("tools/") or not command.endswith(".py"):
            raise RuntimeError(f"{workload_id}: workload command must target a tools/*.py script")
        path = (ROOT / command).resolve()
        if ROOT not in path.parents or not path.is_file():
            raise RuntimeError(f"{workload_id}: workload command is missing or escapes the repository")
        if not marker or not threshold:
            raise RuntimeError(f"{workload_id}: expected marker and threshold source are required")

    policy = data.get("measurement_policy", {})
    if policy.get("cross_engine_runtime_benchmark") != "not_performed":
        raise RuntimeError("cross-engine runtime timings require an identical maintained harness")
    if not str(policy.get("cross_engine_runtime_reason", "")).strip():
        raise RuntimeError("cross-engine non-comparison must include an explicit reason")
    if "shared CI" not in str(policy.get("marketing_policy", "")):
        raise RuntimeError("measurement policy must forbid shared-CI marketing claims")

    references = data.get("external_reference_facts")
    if not isinstance(references, list) or len(references) < 3:
        raise RuntimeError("competitive audit requires at least three explicitly sourced references")
    for item in references:
        if item.get("runtime_performance_compared") is not False:
            raise RuntimeError("external runtime performance must remain unranked without a common harness")
        for key in ("official_url", "distribution_url"):
            value = str(item.get(key, ""))
            if not value.startswith("https://"):
                raise RuntimeError(f"external reference {key} must be an HTTPS URL")
        if not str(item.get("verified_fact", "")).strip():
            raise RuntimeError("external reference fact must not be empty")

    if not DOC_PATH.is_file():
        raise RuntimeError("docs/PERFORMANCE_EVIDENCE_2_0.md is required")
    doc = DOC_PATH.read_text(encoding="utf-8")
    required_doc_phrases = (
        "No cross-engine FPS ranking",
        "Shared CI timing is regression evidence",
        "Arcade",
        "Panda3D",
        "Ursina",
        "Release/PyPI: frozen until SwirEngine 2.0",
    )
    missing = [phrase for phrase in required_doc_phrases if phrase not in doc]
    if missing:
        raise RuntimeError(f"performance evidence documentation is incomplete: {missing}")
    return data


def _commit_sha() -> str:
    value = os.environ.get("GITHUB_SHA", "").strip()
    if value:
        return value
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _runtime_context() -> dict[str, Any]:
    return {
        "commit": _commit_sha(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
    }


def _run_workload(workload: dict[str, Any]) -> dict[str, Any]:
    command = str(workload["command"])
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, command],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    elapsed = time.perf_counter() - started
    stdout = completed.stdout[-MAX_OUTPUT_CHARS:]
    stderr = completed.stderr[-MAX_OUTPUT_CHARS:]
    if completed.returncode != 0:
        raise RuntimeError(
            f"{workload['id']}: workload failed with exit {completed.returncode}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    marker = str(workload["expected_marker"])
    if marker not in stdout:
        raise RuntimeError(f"{workload['id']}: expected evidence marker {marker!r} was not emitted")
    return {
        "id": workload["id"],
        "category": workload["category"],
        "command": f"{sys.executable} {command}",
        "threshold_source": workload["threshold_source"],
        "harness_elapsed_seconds": round(elapsed, 6),
        "stdout": stdout.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SwirEngine 2.0 performance evidence contracts")
    parser.add_argument("--validate-only", action="store_true", help="validate evidence metadata without running workloads")
    parser.add_argument("--output", type=Path, help="optional JSON file for contextual runtime observations")
    args = parser.parse_args()

    contract = _load_contract()
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "scope": contract["scope"],
        "context": _runtime_context(),
        "measurement_policy": contract["measurement_policy"],
        "results": [],
    }
    if not args.validate_only:
        evidence["results"] = [_run_workload(item) for item in contract["workloads"]]

    if args.output is not None:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mode = "metadata" if args.validate_only else f"{len(evidence['results'])} workloads"
    print(
        "SwirEngine 2.0 performance evidence OK: "
        f"{mode}; cross-engine runtime ranking=not performed; commit={evidence['context']['commit']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
