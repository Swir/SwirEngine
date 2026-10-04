from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from tools._release_adapter_2_2_1 import load_isolated_release_module
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from _release_adapter_2_2_1 import load_isolated_release_module

EXPECTED_PACKAGE = "swirengine"
EXPECTED_VERSION = "2.2.1"
SCHEMA = "swirengine-release-provenance-v2"
CHECKSUMS_NAME = "SHA256SUMS"
PROVENANCE_NAME = "release-provenance.json"
DEFAULT_WORKFLOW_MANIFEST = Path(".github/release-gates/2.2.1-required-workflows.json")
EXPECTED_DISTRIBUTIONS = (
    "swirengine-2.2.1-cp314-cp314-win_amd64.whl",
    "swirengine-2.2.1-py3-none-any.whl",
    "swirengine-2.2.1.tar.gz",
)

_BASE: Any = load_isolated_release_module(
    "release_evidence_2_2.py",
    "tools._release_evidence_2_2_1_base",
)
_BASE.EXPECTED_PACKAGE = EXPECTED_PACKAGE
_BASE.EXPECTED_VERSION = EXPECTED_VERSION
_BASE.SCHEMA = SCHEMA
_BASE.CHECKSUMS_NAME = CHECKSUMS_NAME
_BASE.PROVENANCE_NAME = PROVENANCE_NAME
_BASE.DEFAULT_WORKFLOW_MANIFEST = DEFAULT_WORKFLOW_MANIFEST
_BASE.EXPECTED_DISTRIBUTIONS = EXPECTED_DISTRIBUTIONS

ReleaseEvidenceError = _BASE.ReleaseEvidenceError
sha256_file = _BASE.sha256_file
logical_sdist_sha256 = _BASE.logical_sdist_sha256
render_checksums = _BASE.render_checksums


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
    return _BASE.build_provenance(
        dist_dir,
        candidate_source_commit=candidate_source_commit,
        candidate_marker_commit=candidate_marker_commit,
        publication_commit=publication_commit,
        workflow_manifest=workflow_manifest,
        expected_workflow_manifest_sha256=expected_workflow_manifest_sha256,
        expected_logical_sdist_sha256=expected_logical_sdist_sha256,
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
    return _BASE.write_evidence(
        dist_dir,
        candidate_source_commit=candidate_source_commit,
        candidate_marker_commit=candidate_marker_commit,
        publication_commit=publication_commit,
        workflow_manifest=workflow_manifest,
        expected_workflow_manifest_sha256=expected_workflow_manifest_sha256,
        expected_logical_sdist_sha256=expected_logical_sdist_sha256,
    )


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
    return _BASE.verify_evidence(
        dist_dir,
        candidate_source_commit=candidate_source_commit,
        candidate_marker_commit=candidate_marker_commit,
        publication_commit=publication_commit,
        workflow_manifest=workflow_manifest,
        expected_workflow_manifest_sha256=expected_workflow_manifest_sha256,
        expected_logical_sdist_sha256=expected_logical_sdist_sha256,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or verify deterministic SwirEngine 2.2.1 release evidence."
    )
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--candidate-source-commit", required=True)
    parser.add_argument("--candidate-marker-commit", required=True)
    parser.add_argument("--publication-commit", required=True)
    parser.add_argument("--workflow-manifest", type=Path, default=DEFAULT_WORKFLOW_MANIFEST)
    parser.add_argument("--expected-workflow-manifest-sha256", required=True)
    parser.add_argument("--expected-logical-sdist-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.dist_dir.is_dir():
        print(f"SwirEngine 2.2.1 release evidence FAILED: missing dist: {args.dist_dir}")
        return 1
    options = {
        "candidate_source_commit": args.candidate_source_commit,
        "candidate_marker_commit": args.candidate_marker_commit,
        "publication_commit": args.publication_commit,
        "workflow_manifest": args.workflow_manifest,
        "expected_workflow_manifest_sha256": args.expected_workflow_manifest_sha256,
        "expected_logical_sdist_sha256": args.expected_logical_sdist_sha256,
    }
    try:
        if args.mode == "generate":
            checksums, provenance = write_evidence(args.dist_dir, **options)
            print(f"wrote {checksums}")
            print(f"wrote {provenance}")
            return 0
        errors = verify_evidence(args.dist_dir, **options)
    except (OSError, ReleaseEvidenceError) as exc:
        print(f"SwirEngine 2.2.1 release evidence FAILED: {exc}")
        return 1
    if errors:
        print("SwirEngine 2.2.1 release evidence verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SwirEngine 2.2.1 release evidence verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
