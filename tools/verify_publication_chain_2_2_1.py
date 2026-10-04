from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from tools._release_adapter_2_2_1 import load_isolated_release_module
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from _release_adapter_2_2_1 import load_isolated_release_module

EXPECTED_VERSION = "2.2.1"
EXPECTED_TAG = "v2.2.1"
MANIFEST_PATH = PurePosixPath(".github/release-gates/2.2.1-required-workflows.json")
MARKER_ROOT = PurePosixPath(".release/publish-2.2.1")
CANDIDATE_MARKER_PATH = MARKER_ROOT / "candidate.json"
PUBLICATION_MARKER_PATH = MARKER_ROOT / "publication.json"

_BASE: Any = load_isolated_release_module(
    "verify_publication_chain_2_2.py",
    "tools._verify_publication_chain_2_2_1_base",
)
_BASE.EXPECTED_VERSION = EXPECTED_VERSION
_BASE.EXPECTED_TAG = EXPECTED_TAG
_BASE.MANIFEST_PATH = MANIFEST_PATH
_BASE.MARKER_ROOT = MARKER_ROOT
_BASE.CANDIDATE_MARKER_PATH = CANDIDATE_MARKER_PATH
_BASE.PUBLICATION_MARKER_PATH = PUBLICATION_MARKER_PATH

PublicationChainError = _BASE.PublicationChainError
PublicationChain = _BASE.PublicationChain
candidate_marker = _BASE.candidate_marker
publication_marker = _BASE.publication_marker
verify_chain = _BASE.verify_chain
verify_tag = _BASE.verify_tag


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the immutable two-marker SwirEngine 2.2.1 publication chain."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--publication-sha", required=True)
    parser.add_argument(
        "--tag-policy",
        choices=("ignore", "absent-or-publication", "publication"),
        default="ignore",
    )
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        chain = verify_chain(args.root, args.publication_sha)
        verify_tag(args.root, chain.publication_sha, policy=args.tag_policy)
        if args.github_output is not None:
            _BASE._write_github_output(args.github_output, chain)
    except (OSError, PublicationChainError) as exc:
        print(f"SwirEngine 2.2.1 publication chain FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "SwirEngine 2.2.1 publication chain PASS: "
        f"{chain.candidate_source_sha} -> {chain.candidate_marker_sha} -> "
        f"{chain.publication_sha}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
