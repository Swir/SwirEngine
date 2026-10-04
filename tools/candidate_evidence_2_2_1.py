from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from tools._release_adapter_2_2_1 import load_isolated_release_module
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from _release_adapter_2_2_1 import load_isolated_release_module

EXPECTED_REPOSITORY = "Swir/SwirEngine"
EXPECTED_PACKAGE = "swirengine"
EXPECTED_VERSION = "2.2.1"
SCHEMA = "swirengine-candidate-provenance-v1"
CHECKSUMS_NAME = "SHA256SUMS"
PROVENANCE_NAME = "candidate-provenance.json"
DEFAULT_WORKFLOW_MANIFEST = Path(".github/release-gates/2.2.1-required-workflows.json")
EXPECTED_DISTRIBUTIONS = (
    "swirengine-2.2.1-cp314-cp314-win_amd64.whl",
    "swirengine-2.2.1-py3-none-any.whl",
    "swirengine-2.2.1.tar.gz",
)

_BASE: Any = load_isolated_release_module(
    "candidate_evidence_2_2.py",
    "tools._candidate_evidence_2_2_1_base",
)
_BASE.EXPECTED_REPOSITORY = EXPECTED_REPOSITORY
_BASE.EXPECTED_PACKAGE = EXPECTED_PACKAGE
_BASE.EXPECTED_VERSION = EXPECTED_VERSION
_BASE.SCHEMA = SCHEMA
_BASE.CHECKSUMS_NAME = CHECKSUMS_NAME
_BASE.PROVENANCE_NAME = PROVENANCE_NAME
_BASE.DEFAULT_WORKFLOW_MANIFEST = DEFAULT_WORKFLOW_MANIFEST
_BASE.EXPECTED_DISTRIBUTIONS = EXPECTED_DISTRIBUTIONS

CandidateEvidenceError = _BASE.CandidateEvidenceError
sha256_file = _BASE.sha256_file
render_provenance = _BASE.render_provenance
render_checksums = _BASE.render_checksums


def build_provenance(
    dist_dir: Path,
    *,
    source_sha: str,
    workflow_manifest: Path = DEFAULT_WORKFLOW_MANIFEST,
) -> dict[str, Any]:
    return _BASE.build_provenance(
        dist_dir,
        source_sha=source_sha,
        workflow_manifest=workflow_manifest,
    )


def write_evidence(
    dist_dir: Path,
    *,
    source_sha: str,
    workflow_manifest: Path = DEFAULT_WORKFLOW_MANIFEST,
) -> tuple[Path, Path]:
    return _BASE.write_evidence(
        dist_dir,
        source_sha=source_sha,
        workflow_manifest=workflow_manifest,
    )


def verify_evidence(
    dist_dir: Path,
    *,
    source_sha: str,
    workflow_manifest: Path = DEFAULT_WORKFLOW_MANIFEST,
) -> list[str]:
    return _BASE.verify_evidence(
        dist_dir,
        source_sha=source_sha,
        workflow_manifest=workflow_manifest,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or verify deterministic SwirEngine 2.2.1 candidate evidence."
    )
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-manifest", type=Path, default=DEFAULT_WORKFLOW_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
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
        print(f"SwirEngine 2.2.1 candidate evidence FAILED: {exc}")
        return 1
    if errors:
        print("SwirEngine 2.2.1 candidate evidence verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SwirEngine 2.2.1 candidate evidence verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
