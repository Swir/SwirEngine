from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from tools.verify_sdist_identity_2_2 import SdistIdentityError, inspect_sdist
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from verify_sdist_identity_2_2 import SdistIdentityError, inspect_sdist

EXPECTED_PACKAGE = "swirengine"
EXPECTED_VERSION = "2.2.0"
SCHEMA = "swirengine-release-provenance-v2"
CHECKSUMS_NAME = "SHA256SUMS"
PROVENANCE_NAME = "release-provenance.json"
DEFAULT_WORKFLOW_MANIFEST = Path(".github/release-gates/2.2-required-workflows.json")
EXPECTED_DISTRIBUTIONS = (
    f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}-cp314-cp314-win_amd64.whl",
    f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}-py3-none-any.whl",
    f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}.tar.gz",
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReleaseEvidenceError(ValueError):
    """Raised when 2.2 release evidence cannot be constructed safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_commit(value: str, *, field: str) -> str:
    if not _COMMIT_RE.fullmatch(value):
        raise ReleaseEvidenceError(
            f"{field} must be exactly 40 lowercase hexadecimal characters"
        )
    return value


def _require_sha256(value: str, *, field: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ReleaseEvidenceError(
            f"{field} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _distribution_paths(dist_dir: Path) -> tuple[Path, ...]:
    actual = sorted(
        path.name
        for path in dist_dir.iterdir()
        if path.is_file() and (path.name.endswith(".whl") or path.name.endswith(".tar.gz"))
    )
    expected = sorted(EXPECTED_DISTRIBUTIONS)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        details: list[str] = []
        if missing:
            details.append(f"missing distributions: {missing!r}")
        if extra:
            details.append(f"unexpected distributions: {extra!r}")
        raise ReleaseEvidenceError("; ".join(details))
    return tuple(dist_dir / name for name in expected)


def logical_sdist_sha256(path: Path) -> str:
    """Use the single fail-closed logical-sdist identity contract for release evidence."""

    try:
        return inspect_sdist(path).digest
    except SdistIdentityError as exc:
        raise ReleaseEvidenceError(f"unsafe source distribution: {exc}") from exc


def build_provenance(
    dist_dir: Path,
    *,
    candidate_source_commit: str,
    candidate_marker_commit: str,
    publication_commit: str,
    workflow_manifest: Path,
    expected_workflow_manifest_sha256: str,
    expected_logical_sdist_sha256: str,
) -> dict[str, Any]:
    candidate_source_commit = _require_commit(
        candidate_source_commit, field="candidate_source_commit"
    )
    candidate_marker_commit = _require_commit(
        candidate_marker_commit, field="candidate_marker_commit"
    )
    publication_commit = _require_commit(publication_commit, field="publication_commit")
    if len({candidate_source_commit, candidate_marker_commit, publication_commit}) != 3:
        raise ReleaseEvidenceError(
            "candidate source, candidate marker and publication commits must be distinct"
        )
    if not workflow_manifest.is_file():
        raise ReleaseEvidenceError(f"workflow manifest is missing: {workflow_manifest}")
    expected_manifest_digest = _require_sha256(
        expected_workflow_manifest_sha256,
        field="expected_workflow_manifest_sha256",
    )
    actual_manifest_digest = sha256_file(workflow_manifest)
    if actual_manifest_digest != expected_manifest_digest:
        raise ReleaseEvidenceError(
            "workflow manifest digest differs from the accepted candidate: "
            f"{actual_manifest_digest} != {expected_manifest_digest}"
        )

    paths = _distribution_paths(dist_dir)
    sdist = dist_dir / f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}.tar.gz"
    logical_digest = logical_sdist_sha256(sdist)
    expected_digest = _require_sha256(
        expected_logical_sdist_sha256,
        field="expected_logical_sdist_sha256",
    )
    if logical_digest != expected_digest:
        raise ReleaseEvidenceError(
            "logical sdist digest differs from the accepted candidate: "
            f"{logical_digest} != {expected_digest}"
        )

    return {
        "schema": SCHEMA,
        "package": EXPECTED_PACKAGE,
        "version": EXPECTED_VERSION,
        "candidate_source_commit": candidate_source_commit,
        "candidate_marker_commit": candidate_marker_commit,
        "publication_commit": publication_commit,
        "hash_algorithm": "sha256",
        "workflow_manifest_sha256": actual_manifest_digest,
        "logical_sdist_sha256": logical_digest,
        "artifacts": [
            {
                "name": path.name,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in paths
        ],
    }


def render_checksums(provenance: Mapping[str, Any]) -> str:
    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReleaseEvidenceError("provenance artifacts must be a list")
    return "".join(
        f"{artifact['sha256']}  {artifact['name']}\n"
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    )


def write_evidence(
    dist_dir: Path,
    *,
    candidate_source_commit: str,
    candidate_marker_commit: str,
    publication_commit: str,
    workflow_manifest: Path,
    expected_workflow_manifest_sha256: str,
    expected_logical_sdist_sha256: str,
) -> tuple[Path, Path]:
    provenance = build_provenance(
        dist_dir,
        candidate_source_commit=candidate_source_commit,
        candidate_marker_commit=candidate_marker_commit,
        publication_commit=publication_commit,
        workflow_manifest=workflow_manifest,
        expected_workflow_manifest_sha256=expected_workflow_manifest_sha256,
        expected_logical_sdist_sha256=expected_logical_sdist_sha256,
    )
    checksums_path = dist_dir / CHECKSUMS_NAME
    provenance_path = dist_dir / PROVENANCE_NAME
    checksums_path.write_text(render_checksums(provenance), encoding="utf-8")
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return checksums_path, provenance_path


def verify_evidence(
    dist_dir: Path,
    *,
    candidate_source_commit: str,
    candidate_marker_commit: str,
    publication_commit: str,
    workflow_manifest: Path,
    expected_workflow_manifest_sha256: str,
    expected_logical_sdist_sha256: str,
) -> list[str]:
    expected = build_provenance(
        dist_dir,
        candidate_source_commit=candidate_source_commit,
        candidate_marker_commit=candidate_marker_commit,
        publication_commit=publication_commit,
        workflow_manifest=workflow_manifest,
        expected_workflow_manifest_sha256=expected_workflow_manifest_sha256,
        expected_logical_sdist_sha256=expected_logical_sdist_sha256,
    )
    errors: list[str] = []
    checksums_path = dist_dir / CHECKSUMS_NAME
    provenance_path = dist_dir / PROVENANCE_NAME
    if not checksums_path.is_file():
        errors.append(f"missing {CHECKSUMS_NAME}")
    if not provenance_path.is_file():
        errors.append(f"missing {PROVENANCE_NAME}")
    if errors:
        return errors

    try:
        actual = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"invalid {PROVENANCE_NAME}: {exc}")
        actual = None
    if actual != expected:
        errors.append("release provenance does not match exact artifacts and release chain")
    if checksums_path.read_text(encoding="utf-8") != render_checksums(expected):
        errors.append("SHA256SUMS does not match exact candidate distributions")
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or verify deterministic SwirEngine 2.2 release evidence.",
    )
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--candidate-source-commit", required=True)
    parser.add_argument("--candidate-marker-commit", required=True)
    parser.add_argument("--publication-commit", required=True)
    parser.add_argument(
        "--workflow-manifest",
        type=Path,
        default=DEFAULT_WORKFLOW_MANIFEST,
    )
    parser.add_argument("--expected-workflow-manifest-sha256", required=True)
    parser.add_argument("--expected-logical-sdist-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.dist_dir.is_dir():
        print(f"SwirEngine 2.2 release evidence FAILED: missing dist directory: {args.dist_dir}")
        return 1
    try:
        options = {
            "candidate_source_commit": args.candidate_source_commit,
            "candidate_marker_commit": args.candidate_marker_commit,
            "publication_commit": args.publication_commit,
            "workflow_manifest": args.workflow_manifest,
            "expected_workflow_manifest_sha256": args.expected_workflow_manifest_sha256,
            "expected_logical_sdist_sha256": args.expected_logical_sdist_sha256,
        }
        if args.mode == "generate":
            checksums, provenance = write_evidence(args.dist_dir, **options)
            print(f"wrote {checksums}")
            print(f"wrote {provenance}")
            return 0
        errors = verify_evidence(args.dist_dir, **options)
    except (OSError, ReleaseEvidenceError) as exc:
        print(f"SwirEngine 2.2 release evidence FAILED: {exc}")
        return 1
    if errors:
        print("SwirEngine 2.2 release evidence verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SwirEngine 2.2 release evidence verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
