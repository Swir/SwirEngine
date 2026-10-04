from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPECTED_REPOSITORY = "Swir/SwirEngine"
EXPECTED_BASE_REF = "main"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class CandidateMergeError(ValueError):
    """Raised when candidate-to-main merge provenance cannot be proven exactly."""


@dataclass(frozen=True, slots=True)
class CandidateMerge:
    candidate_sha: str
    merge_commit_sha: str
    base_parent_sha: str
    main_sha: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateMergeError(message)


def _require_mapping(value: object, subject: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{subject} must be a JSON object")
    assert isinstance(value, Mapping)
    return value


def _require_repository(container: Mapping[str, Any], subject: str) -> None:
    repository = _require_mapping(container.get("repo"), f"{subject}.repo")
    full_name = repository.get("full_name")
    _require(
        full_name == EXPECTED_REPOSITORY,
        f"{subject}.repo.full_name must be exactly {EXPECTED_REPOSITORY}",
    )


def _parse_pull(payload: object, candidate_sha: str) -> str:
    _require(bool(SHA_RE.fullmatch(candidate_sha)), "candidate SHA must be canonical lowercase hex")
    _require(isinstance(payload, list), "pulls JSON must be a top-level array")
    assert isinstance(payload, list)
    _require(
        len(payload) == 1,
        f"pulls JSON must contain exactly one pull request; found {len(payload)}",
    )

    pull = _require_mapping(payload[0], "pull request")
    head = _require_mapping(pull.get("head"), "pull request head")
    _require_repository(head, "pull request head")
    head_sha = head.get("sha")
    _require(
        head_sha == candidate_sha,
        f"pull request head SHA must be exact candidate {candidate_sha}; got {head_sha!r}",
    )

    base = _require_mapping(pull.get("base"), "pull request base")
    _require_repository(base, "pull request base")
    _require(
        base.get("ref") == EXPECTED_BASE_REF,
        f"pull request base.ref must be exactly {EXPECTED_BASE_REF}",
    )

    merged_at = pull.get("merged_at")
    _require(
        isinstance(merged_at, str) and bool(merged_at.strip()),
        "pull request must be merged (merged_at is missing)",
    )
    merge_commit_sha = pull.get("merge_commit_sha")
    _require(
        isinstance(merge_commit_sha, str) and bool(SHA_RE.fullmatch(merge_commit_sha)),
        "pull request merge_commit_sha must be canonical lowercase hex",
    )
    assert isinstance(merge_commit_sha, str)
    return merge_commit_sha


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=check,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise CandidateMergeError(f"could not run git: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        suffix = f": {detail}" if detail else ""
        raise CandidateMergeError(f"git {' '.join(args)} failed{suffix}") from exc


def _resolve_commit(root: Path, revision: str, subject: str) -> str:
    result = _git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    value = result.stdout.strip()
    _require(
        bool(SHA_RE.fullmatch(value)),
        f"{subject} did not resolve to a canonical commit SHA",
    )
    return value


def _require_ancestor(root: Path, ancestor: str, descendant: str, message: str) -> None:
    result = _git(root, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if result.returncode == 1:
        raise CandidateMergeError(message)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        suffix = f": {detail}" if detail else ""
        raise CandidateMergeError(f"could not verify Git ancestry{suffix}")


def _merge_parents(root: Path, merge_commit_sha: str) -> tuple[str, str]:
    result = _git(root, "show", "-s", "--format=%P", merge_commit_sha)
    parents = result.stdout.strip().split()
    _require(
        len(parents) == 2,
        "canonical merge commit must be a normal merge with exactly two parents; "
        f"found {len(parents)}",
    )
    first_parent, second_parent = parents
    _require(
        bool(SHA_RE.fullmatch(first_parent)) and bool(SHA_RE.fullmatch(second_parent)),
        "canonical merge commit parents must be canonical lowercase commit SHAs",
    )
    return first_parent, second_parent


def verify_candidate_merge(
    payload: object,
    *,
    candidate_sha: str,
    root: Path,
    main_ref: str = "origin/main",
) -> CandidateMerge:
    merge_commit_sha = _parse_pull(payload, candidate_sha)
    root = root.resolve()

    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    _require(inside.stdout.strip() == "true", f"not a Git worktree: {root}")

    resolved_candidate = _resolve_commit(root, candidate_sha, "candidate source")
    _require(
        resolved_candidate == candidate_sha,
        "candidate source did not resolve to its exact requested commit",
    )
    resolved_merge = _resolve_commit(root, merge_commit_sha, "merge commit")
    _require(
        resolved_merge == merge_commit_sha,
        "merge commit did not resolve to its exact GitHub commit",
    )
    main_sha = _resolve_commit(root, main_ref, f"main ref {main_ref}")

    _require_ancestor(
        root,
        candidate_sha,
        merge_commit_sha,
        "candidate source is not an ancestor of the canonical merge commit",
    )

    base_parent_sha, candidate_parent_sha = _merge_parents(root, merge_commit_sha)
    _require(
        candidate_parent_sha == candidate_sha,
        "canonical merge commit second parent must be the exact candidate source "
        f"{candidate_sha}; got {candidate_parent_sha}",
    )

    _require_ancestor(
        root,
        merge_commit_sha,
        main_sha,
        f"canonical merge commit is not an ancestor of fresh main ref {main_ref}",
    )

    return CandidateMerge(
        candidate_sha=candidate_sha,
        merge_commit_sha=merge_commit_sha,
        base_parent_sha=base_parent_sha,
        main_sha=main_sha,
    )


def _write_github_output(path: Path, result: CandidateMerge) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"merge_commit_sha={result.merge_commit_sha}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify exact SwirEngine 2.2 candidate-to-main merge provenance.",
    )
    parser.add_argument("--pulls-json", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--main-ref", default="origin/main")
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = json.loads(args.pulls_json.read_text(encoding="utf-8"))
        result = verify_candidate_merge(
            payload,
            candidate_sha=args.candidate_sha,
            root=args.root,
            main_ref=args.main_ref,
        )
        if args.github_output is not None:
            _write_github_output(args.github_output, result)
    except (json.JSONDecodeError, OSError, CandidateMergeError) as exc:
        print(f"Candidate merge verification FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "Candidate merge PASS: "
        f"{result.candidate_sha} -> {result.merge_commit_sha} -> {args.main_ref} "
        f"({result.main_sha})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
