from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
EXPECTED_REPOSITORY = "Swir/SwirEngine"
DEFAULT_MANIFEST = Path(".github/release-gates/2.2-required-workflows.json")
MODE_EVENTS = {
    "pull-request": "pull_request",
    "push": "push",
}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
WORKFLOW_NAME_RE = re.compile(r"^name:\s*(?P<name>.*?)\s*$", re.MULTILINE)


class WorkflowVerificationError(ValueError):
    """Raised when the required-workflow contract fails closed."""


@dataclass(frozen=True, slots=True)
class RequiredWorkflow:
    path: str
    name: str


@dataclass(frozen=True, slots=True)
class RequiredWorkflowManifest:
    repository: str
    workflows: tuple[RequiredWorkflow, ...]


@dataclass(frozen=True, slots=True)
class WorkflowRunReport:
    repository: str
    head_sha: str
    event: str
    verified: tuple[RequiredWorkflow, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowVerificationError(message)


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], subject: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"missing keys: {', '.join(missing)}")
    if unexpected:
        details.append(f"unexpected keys: {', '.join(unexpected)}")
    _require(not details, f"{subject} has an invalid schema ({'; '.join(details)})")


def parse_manifest(data: object) -> RequiredWorkflowManifest:
    _require(isinstance(data, Mapping), "required-workflow manifest must be a JSON object")
    assert isinstance(data, Mapping)
    _require_exact_keys(
        data,
        {"schema_version", "repository", "required_workflows"},
        "required-workflow manifest",
    )
    _require(
        data["schema_version"] == SCHEMA_VERSION,
        f"required-workflow manifest schema_version must be {SCHEMA_VERSION}",
    )
    repository = data["repository"]
    _require(
        repository == EXPECTED_REPOSITORY,
        f"required-workflow manifest repository must be {EXPECTED_REPOSITORY}",
    )
    entries = data["required_workflows"]
    _require(
        isinstance(entries, list) and bool(entries),
        "required_workflows must be a non-empty JSON array",
    )

    workflows: list[RequiredWorkflow] = []
    paths: set[str] = set()
    names: set[str] = set()
    for index, entry in enumerate(entries):
        subject = f"required_workflows[{index}]"
        _require(isinstance(entry, Mapping), f"{subject} must be a JSON object")
        assert isinstance(entry, Mapping)
        _require_exact_keys(entry, {"path", "name"}, subject)
        path = entry["path"]
        name = entry["name"]
        _require(isinstance(path, str) and bool(path), f"{subject}.path must be non-empty")
        _require(isinstance(name, str) and bool(name), f"{subject}.name must be non-empty")
        assert isinstance(path, str)
        assert isinstance(name, str)

        pure_path = PurePosixPath(path)
        _require("\\" not in path, f"{subject}.path must use POSIX separators")
        _require(
            not pure_path.is_absolute() and pure_path.as_posix() == path,
            f"{subject}.path must be a canonical relative path",
        )
        _require(
            len(pure_path.parts) == 3
            and pure_path.parts[:2] == (".github", "workflows")
            and pure_path.suffix in {".yml", ".yaml"},
            f"{subject}.path must name one YAML file under .github/workflows",
        )
        _require(path not in paths, f"duplicate required workflow path: {path}")
        _require(name not in names, f"duplicate required workflow name: {name}")
        paths.add(path)
        names.add(name)
        workflows.append(RequiredWorkflow(path=path, name=name))

    return RequiredWorkflowManifest(
        repository=str(repository),
        workflows=tuple(workflows),
    )


def load_manifest(path: Path) -> RequiredWorkflowManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowVerificationError(f"invalid JSON manifest {path}: {exc}") from exc
    return parse_manifest(data)


def _parse_workflow_name(text: str, path: str) -> str:
    matches = list(WORKFLOW_NAME_RE.finditer(text))
    _require(len(matches) == 1, f"{path} must contain exactly one top-level workflow name")
    value = matches[0].group("name")
    _require(bool(value), f"{path} has an empty top-level workflow name")
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise WorkflowVerificationError(
                f"{path} has an invalid quoted top-level workflow name"
            ) from exc
        _require(isinstance(decoded, str), f"{path} workflow name must be a string")
        return decoded
    if value.startswith("'"):
        _require(
            len(value) >= 2 and value.endswith("'"),
            f"{path} has an invalid quoted top-level workflow name",
        )
        return value[1:-1].replace("''", "'")
    return value


def verify_manifest_files(
    manifest: RequiredWorkflowManifest,
    root: Path,
) -> tuple[RequiredWorkflow, ...]:
    root = root.resolve()
    for workflow in manifest.workflows:
        path = root / workflow.path
        _require(path.is_file(), f"required workflow file is missing: {workflow.path}")
        actual_name = _parse_workflow_name(path.read_text(encoding="utf-8"), workflow.path)
        _require(
            actual_name == workflow.name,
            f"unexpected workflow name for {workflow.path}: "
            f"expected {workflow.name!r}, got {actual_name!r}",
        )
    return manifest.workflows


def _workflow_runs(payload: object) -> Sequence[object]:
    if isinstance(payload, list):
        return payload
    _require(
        isinstance(payload, Mapping),
        "workflow-run payload must be an array or a GitHub workflow-runs object",
    )
    assert isinstance(payload, Mapping)
    runs = payload.get("workflow_runs")
    _require(isinstance(runs, list), "workflow-run payload is missing workflow_runs array")
    total_count = payload.get("total_count")
    if total_count is not None:
        _require(
            isinstance(total_count, int) and not isinstance(total_count, bool),
            "workflow-run payload total_count must be an integer",
        )
        _require(
            total_count == len(runs),
            "workflow-run payload is incomplete: total_count does not match supplied runs",
        )
    return runs


def _run_repository(run: Mapping[str, Any], index: int) -> str:
    repository = run.get("repository")
    _require(
        isinstance(repository, Mapping),
        f"workflow_runs[{index}].repository must be an object",
    )
    assert isinstance(repository, Mapping)
    full_name = repository.get("full_name")
    _require(
        isinstance(full_name, str) and bool(full_name),
        f"workflow_runs[{index}].repository.full_name must be non-empty",
    )
    return str(full_name)


def _head_repository(run: Mapping[str, Any], index: int) -> str:
    repository = run.get("head_repository")
    _require(
        isinstance(repository, Mapping),
        f"workflow_runs[{index}].head_repository must be an object",
    )
    assert isinstance(repository, Mapping)
    full_name = repository.get("full_name")
    _require(
        isinstance(full_name, str) and bool(full_name),
        f"workflow_runs[{index}].head_repository.full_name must be non-empty",
    )
    return str(full_name)


def _run_order(run: Mapping[str, Any], index: int) -> tuple[int, int, int]:
    values: list[int] = []
    for field in ("run_number", "run_attempt", "id"):
        value = run.get(field)
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value > 0,
            f"workflow_runs[{index}].{field} must be a positive integer",
        )
        values.append(value)
    return values[0], values[1], values[2]


def verify_workflow_runs(
    manifest: RequiredWorkflowManifest,
    payload: object,
    *,
    head_sha: str,
    mode: str,
) -> WorkflowRunReport:
    _require(mode in MODE_EVENTS, f"unsupported workflow verification mode: {mode}")
    _require(bool(SHA_RE.fullmatch(head_sha)), "head SHA must be exactly 40 hexadecimal digits")
    expected_sha = head_sha.lower()
    expected_event = MODE_EVENTS[mode]
    parsed_runs: list[tuple[Mapping[str, Any], tuple[int, int, int]]] = []

    for index, run in enumerate(_workflow_runs(payload)):
        _require(isinstance(run, Mapping), f"workflow_runs[{index}] must be an object")
        assert isinstance(run, Mapping)
        for field in ("path", "name", "head_sha", "event", "status", "conclusion"):
            _require(
                isinstance(run.get(field), str),
                f"workflow_runs[{index}].{field} must be a string",
            )
        actual_sha = str(run["head_sha"])
        _require(
            actual_sha.lower() == expected_sha,
            f"workflow_runs[{index}] is for unexpected head SHA {actual_sha}",
        )
        actual_repository = _run_repository(run, index)
        _require(
            actual_repository == manifest.repository,
            f"workflow_runs[{index}] is for unexpected repository {actual_repository}",
        )
        source_repository = _head_repository(run, index)
        _require(
            source_repository == manifest.repository,
            f"workflow_runs[{index}] has unexpected head repository {source_repository}",
        )
        parsed_runs.append((run, _run_order(run, index)))

    verified: list[RequiredWorkflow] = []
    for workflow in manifest.workflows:
        candidates = [
            (run, order)
            for run, order in parsed_runs
            if run["path"] == workflow.path and run["event"] == expected_event
        ]
        _require(
            bool(candidates),
            f"missing {expected_event} run for required workflow {workflow.path}",
        )
        orders = [order for _, order in candidates]
        _require(
            len(orders) == len(set(orders)),
            f"ambiguous duplicate {expected_event} run identity for {workflow.path}",
        )
        run, _ = max(candidates, key=lambda candidate: candidate[1])
        _require(
            run["name"] == workflow.name,
            f"unexpected workflow name for {workflow.path}: "
            f"expected {workflow.name!r}, got {run['name']!r}",
        )
        _require(
            run["status"] == "completed",
            f"required workflow is not completed: {workflow.path}",
        )
        _require(
            run["conclusion"] == "success",
            f"required workflow did not conclude successfully: {workflow.path}",
        )
        verified.append(workflow)

    return WorkflowRunReport(
        repository=manifest.repository,
        head_sha=expected_sha,
        event=expected_event,
        verified=tuple(verified),
    )


def _resolve_from_root(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the explicit SwirEngine 2.2 required-workflow contract.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the root containing this script)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="manifest path, relative to --root by default",
    )
    parser.add_argument(
        "--runs-json",
        type=Path,
        help="optional saved GitHub workflow-runs JSON response",
    )
    parser.add_argument("--sha", help="exact 40-character head SHA for --runs-json")
    parser.add_argument(
        "--mode",
        choices=tuple(MODE_EVENTS),
        help="required GitHub event for --runs-json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    run_options = (args.runs_json, args.sha, args.mode)
    if any(option is not None for option in run_options) and not all(
        option is not None for option in run_options
    ):
        parser.error("--runs-json, --sha, and --mode must be supplied together")

    root = args.root.resolve()
    manifest_path = _resolve_from_root(root, args.manifest)
    try:
        manifest = load_manifest(manifest_path)
        verified_files = verify_manifest_files(manifest, root)
        print(
            f"Required workflow manifest PASS: {len(verified_files)} workflows "
            f"for {manifest.repository}"
        )
        if args.runs_json is not None:
            runs_path = _resolve_from_root(root, args.runs_json)
            payload = json.loads(runs_path.read_text(encoding="utf-8"))
            report = verify_workflow_runs(
                manifest,
                payload,
                head_sha=args.sha,
                mode=args.mode,
            )
            print(
                f"Required workflow runs PASS: {len(report.verified)} {report.event} "
                f"workflows at {report.head_sha}"
            )
    except (OSError, json.JSONDecodeError, WorkflowVerificationError) as exc:
        print(f"Required workflow verification FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
