from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from tools.verify_sdist_identity_2_2 import SdistIdentityError, inspect_sdist
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from verify_sdist_identity_2_2 import SdistIdentityError, inspect_sdist

EXPECTED_REPOSITORY = "Swir/SwirEngine"
EXPECTED_PACKAGE = "swirengine"
EXPECTED_VERSION = "2.2.0"
SCHEMA = "swirengine-candidate-provenance-v1"
CHECKSUMS_NAME = "SHA256SUMS"
PROVENANCE_NAME = "candidate-provenance.json"
DEFAULT_WORKFLOW_MANIFEST = Path(".github/release-gates/2.2-required-workflows.json")
EXPECTED_DISTRIBUTIONS = (
    f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}-cp314-cp314-win_amd64.whl",
    f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}-py3-none-any.whl",
    f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}.tar.gz",
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CandidateEvidenceError(ValueError):
    """Raised when exact Phase B candidate evidence cannot be constructed safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_source_sha(value: str) -> str:
    if not _COMMIT_RE.fullmatch(value):
        raise CandidateEvidenceError(
            "candidate source SHA must be exactly 40 lowercase hexadecimal characters"
        )
    return value


def _distribution_paths(dist_dir: Path) -> tuple[Path, ...]:
    if not dist_dir.is_dir():
        raise CandidateEvidenceError(f"distribution directory is missing: {dist_dir}")

    archives = sorted(
        path
        for path in dist_dir.iterdir()
        if path.name.casefold().endswith((".whl", ".tar.gz"))
    )
    actual = [path.name for path in archives]
    expected = sorted(EXPECTED_DISTRIBUTIONS)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        details: list[str] = []
        if missing:
            details.append(f"missing distributions: {missing!r}")
        if extra:
            details.append(f"unexpected distributions: {extra!r}")
        raise CandidateEvidenceError("; ".join(details))

    paths = tuple(dist_dir / name for name in expected)
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise CandidateEvidenceError(
                f"candidate distribution must be a regular non-symlink file: {path.name}"
            )
    return paths


def _manifest_digest(workflow_manifest: Path) -> str:
    if workflow_manifest.is_symlink() or not workflow_manifest.is_file():
        raise CandidateEvidenceError(
            f"workflow manifest must be a regular non-symlink file: {workflow_manifest}"
        )
    return sha256_file(workflow_manifest)


def build_provenance(
    dist_dir: Path,
    *,
    source_sha: str,
    workflow_manifest: Path = DEFAULT_WORKFLOW_MANIFEST,
) -> dict[str, Any]:
    source_sha = _require_source_sha(source_sha)
    paths = _distribution_paths(dist_dir)
    sdist = dist_dir / f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}.tar.gz"
    try:
        logical_sdist_sha256 = inspect_sdist(sdist).digest
    except SdistIdentityError as exc:
        raise CandidateEvidenceError(f"unsafe candidate source distribution: {exc}") from exc

    return {
        "schema": SCHEMA,
        "repository": EXPECTED_REPOSITORY,
        "package": EXPECTED_PACKAGE,
        "version": EXPECTED_VERSION,
        "candidate_source_commit": source_sha,
        "hash_algorithm": "sha256",
        "workflow_manifest_sha256": _manifest_digest(workflow_manifest),
        "logical_sdist_sha256": logical_sdist_sha256,
        "artifacts": [
            {
                "name": path.name,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in paths
        ],
    }


def render_provenance(provenance: Mapping[str, Any]) -> bytes:
    return (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_checksums(provenance: Mapping[str, Any]) -> bytes:
    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, list):
        raise CandidateEvidenceError("candidate provenance artifacts must be a list")
    lines: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise CandidateEvidenceError("candidate provenance artifact must be an object")
        name = artifact.get("name")
        digest = artifact.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            raise CandidateEvidenceError("candidate provenance artifact identity is invalid")
        lines.append(f"{digest}  {name}\n")
    return "".join(lines).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def write_evidence(
    dist_dir: Path,
    *,
    source_sha: str,
    workflow_manifest: Path = DEFAULT_WORKFLOW_MANIFEST,
) -> tuple[Path, Path]:
    provenance = build_provenance(
        dist_dir,
        source_sha=source_sha,
        workflow_manifest=workflow_manifest,
    )
    checksums_path = dist_dir / CHECKSUMS_NAME
    provenance_path = dist_dir / PROVENANCE_NAME
    _atomic_write(checksums_path, render_checksums(provenance))
    _atomic_write(provenance_path, render_provenance(provenance))
    return checksums_path, provenance_path


def verify_evidence(
    dist_dir: Path,
    *,
    source_sha: str,
    workflow_manifest: Path = DEFAULT_WORKFLOW_MANIFEST,
) -> list[str]:
    expected = build_provenance(
        dist_dir,
        source_sha=source_sha,
        workflow_manifest=workflow_manifest,
    )
    expected_checksums = render_checksums(expected)
    expected_provenance = render_provenance(expected)
    errors: list[str] = []

    checksums_path = dist_dir / CHECKSUMS_NAME
    provenance_path = dist_dir / PROVENANCE_NAME
    if checksums_path.is_symlink() or not checksums_path.is_file():
        errors.append(f"missing regular non-symlink {CHECKSUMS_NAME}")
    elif checksums_path.read_bytes() != expected_checksums:
        errors.append("SHA256SUMS is not the canonical checksum set for exact candidate artifacts")

    if provenance_path.is_symlink() or not provenance_path.is_file():
        errors.append(f"missing regular non-symlink {PROVENANCE_NAME}")
    elif provenance_path.read_bytes() != expected_provenance:
        errors.append(
            "candidate provenance is not canonical or does not match exact source/artifacts"
        )
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or verify deterministic SwirEngine 2.2 Phase B candidate evidence.",
    )
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--workflow-manifest",
        type=Path,
        default=DEFAULT_WORKFLOW_MANIFEST,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.mode == "generate":
            checksums, provenance = write_evidence(
                args.dist_dir,
                source_sha=args.source_sha,
                workflow_manifest=args.workflow_manifest,
            )
            print(f"wrote {checksums}")
            print(f"wrote {provenance}")
            return 0

        errors = verify_evidence(
            args.dist_dir,
            source_sha=args.source_sha,
            workflow_manifest=args.workflow_manifest,
        )
    except (OSError, CandidateEvidenceError) as exc:
        print(f"SwirEngine 2.2 candidate evidence FAILED: {exc}")
        return 1

    if errors:
        print("SwirEngine 2.2 candidate evidence verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SwirEngine 2.2 candidate evidence verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
