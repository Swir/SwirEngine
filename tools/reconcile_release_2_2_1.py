from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from tools._release_adapter_2_2_1 import load_isolated_release_module
    from tools.release_evidence_2_2_1 import (
        CHECKSUMS_NAME,
        EXPECTED_DISTRIBUTIONS,
        EXPECTED_PACKAGE,
        EXPECTED_VERSION,
        PROVENANCE_NAME,
        SCHEMA,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from _release_adapter_2_2_1 import load_isolated_release_module
    from release_evidence_2_2_1 import (
        CHECKSUMS_NAME,
        EXPECTED_DISTRIBUTIONS,
        EXPECTED_PACKAGE,
        EXPECTED_VERSION,
        PROVENANCE_NAME,
        SCHEMA,
    )

TAG = "v2.2.1"
EXPECTED_RELEASE_TITLE = "SwirEngine 2.2.1"
DEFAULT_RELEASE_NOTES = Path(__file__).resolve().parents[1] / "RELEASE_NOTES_2_2_1.md"
DEFAULT_PYPI_DESCRIPTION = Path(__file__).resolve().parents[1] / "PYPI_DESCRIPTION_2_2_1.md"
EXPECTED_REQUIRES_PYTHON = frozenset({">=3.10", "<3.15"})

_BASE: Any = load_isolated_release_module(
    "reconcile_release_2_2.py",
    "tools._reconcile_release_2_2_1_base",
)
_BASE.EXPECTED_PACKAGE = EXPECTED_PACKAGE
_BASE.EXPECTED_VERSION = EXPECTED_VERSION
_BASE.EXPECTED_DISTRIBUTIONS = EXPECTED_DISTRIBUTIONS
_BASE.SCHEMA = SCHEMA
_BASE.CHECKSUMS_NAME = CHECKSUMS_NAME
_BASE.PROVENANCE_NAME = PROVENANCE_NAME
_BASE.TAG = TAG
_BASE.EXPECTED_RELEASE_TITLE = EXPECTED_RELEASE_TITLE
_BASE.DEFAULT_RELEASE_NOTES = DEFAULT_RELEASE_NOTES

ReleaseReconciliationError = _BASE.ReleaseReconciliationError
ArtifactIdentity = _BASE.ArtifactIdentity
ReleaseSnapshot = _BASE.ReleaseSnapshot
ReconciliationPlan = _BASE.ReconciliationPlan


@dataclass(frozen=True, slots=True)
class ExpectedRelease:
    publication_commit: str
    release_title: str
    release_body: str
    pypi_description: str
    distributions: tuple[Any, ...]
    release_assets: tuple[Any, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseReconciliationError(message)


def _read_exact_text(path: Path, subject: str) -> str:
    _require(path.is_file() and not path.is_symlink(), f"{subject} is missing or unsafe: {path}")
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseReconciliationError(f"cannot read {subject}: {exc}") from exc
    _require(bool(value), f"{subject} must not be empty")
    return value


def load_expected_release(
    dist_dir: Path,
    *,
    publication_commit: str,
    release_notes: Path = DEFAULT_RELEASE_NOTES,
    pypi_description: Path = DEFAULT_PYPI_DESCRIPTION,
) -> ExpectedRelease:
    base = _BASE.load_expected_release(
        dist_dir,
        publication_commit=publication_commit,
        release_notes=release_notes,
    )
    return ExpectedRelease(
        publication_commit=base.publication_commit,
        release_title=base.release_title,
        release_body=base.release_body,
        pypi_description=_read_exact_text(pypi_description, "PyPI description"),
        distributions=base.distributions,
        release_assets=base.release_assets,
    )


def _validate_pypi_metadata(expected: ExpectedRelease, payload: object | None) -> None:
    if payload is None:
        return
    _require(isinstance(payload, Mapping), "PyPI snapshot must be an object or null")
    assert isinstance(payload, Mapping)
    info = payload.get("info")
    _require(isinstance(info, Mapping), "PyPI snapshot has no info object")
    assert isinstance(info, Mapping)
    _require(
        info.get("description") == expected.pypi_description,
        "PyPI description does not match the exact 2.2.1 package description",
    )
    _require(
        info.get("description_content_type") == "text/markdown",
        "PyPI description_content_type must be exactly text/markdown",
    )
    requires_python = info.get("requires_python")
    _require(isinstance(requires_python, str), "PyPI Requires-Python is missing")
    assert isinstance(requires_python, str)
    normalized = frozenset(part.strip() for part in requires_python.split(",") if part.strip())
    _require(
        normalized == EXPECTED_REQUIRES_PYTHON,
        "PyPI Requires-Python differs from the exact 2.2.1 contract",
    )


def reconcile_release(
    expected: ExpectedRelease,
    snapshot: Any,
) -> Any:
    _validate_pypi_metadata(expected, snapshot.pypi)
    return _BASE.reconcile_release(expected, snapshot)


def reconcile_after_reread(
    expected: ExpectedRelease,
    initial: Any,
    reread: Any,
) -> Any:
    before = reconcile_release(expected, initial)
    after = reconcile_release(expected, reread)
    _require(
        set(after.pypi_uploads).issubset(before.pypi_uploads),
        "PyPI state regressed between initial read and re-read",
    )
    _require(
        set(after.github_uploads).issubset(before.github_uploads),
        "GitHub Release state regressed between initial read and re-read",
    )
    _require(not after.create_tag or before.create_tag, "GitHub tag disappeared after initial read")
    _require(
        not after.create_release or before.create_release,
        "GitHub Release disappeared after initial read",
    )
    return after


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReleaseReconciliationError(f"cannot read JSON snapshot {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan a fail-closed SwirEngine 2.2.1 release retry from saved snapshots."
    )
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--publication-commit", required=True)
    parser.add_argument("--pypi-json", type=Path, required=True)
    parser.add_argument("--tag-json", type=Path, required=True)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--release-notes", type=Path, default=DEFAULT_RELEASE_NOTES)
    parser.add_argument("--pypi-description", type=Path, default=DEFAULT_PYPI_DESCRIPTION)
    parser.add_argument("--initial-pypi-json", type=Path)
    parser.add_argument("--initial-tag-json", type=Path)
    parser.add_argument("--initial-release-json", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    initial_paths = (args.initial_pypi_json, args.initial_tag_json, args.initial_release_json)
    if any(path is not None for path in initial_paths) and not all(
        path is not None for path in initial_paths
    ):
        parser.error(
            "--initial-pypi-json, --initial-tag-json and --initial-release-json "
            "must be supplied together"
        )
    try:
        expected = load_expected_release(
            args.dist_dir,
            publication_commit=args.publication_commit,
            release_notes=args.release_notes,
            pypi_description=args.pypi_description,
        )
        fresh = ReleaseSnapshot(
            pypi=_load_json(args.pypi_json),
            tag=_load_json(args.tag_json),
            release=_load_json(args.release_json),
        )
        if all(path is not None for path in initial_paths):
            initial = ReleaseSnapshot(
                pypi=_load_json(args.initial_pypi_json),
                tag=_load_json(args.initial_tag_json),
                release=_load_json(args.initial_release_json),
            )
            plan = reconcile_after_reread(expected, initial, fresh)
        else:
            plan = reconcile_release(expected, fresh)
    except (OSError, ReleaseReconciliationError) as exc:
        print(f"SwirEngine 2.2.1 release reconciliation FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(plan.as_dict(), sort_keys=True, separators=(",", ":")))
    if args.require_complete and not plan.complete:
        print("SwirEngine 2.2.1 release reconciliation is incomplete", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
