from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

EXPECTED_REPOSITORY = "Swir/SwirEngine"
EXPECTED_VERSION = "2.2.0"
EXPECTED_TAG = "v2.2.0"
SCHEMA_VERSION = 1
MANIFEST_PATH = PurePosixPath(".github/release-gates/2.2-required-workflows.json")
MARKER_ROOT = PurePosixPath(".release/publish-2.2.0")
CANDIDATE_MARKER_PATH = MARKER_ROOT / "candidate.json"
PUBLICATION_MARKER_PATH = MARKER_ROOT / "publication.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PublicationChainError(ValueError):
    """Raised when the immutable 2.2 publication chain is not exact."""


@dataclass(frozen=True, slots=True)
class PublicationChain:
    candidate_source_sha: str
    candidate_marker_sha: str
    publication_sha: str
    workflow_manifest_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationChainError(message)


def _canonical_json(data: Mapping[str, Any]) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def candidate_marker(*, candidate_source_sha: str, manifest_sha256: str) -> bytes:
    _require_sha(candidate_source_sha, "candidate source SHA")
    _require_digest(manifest_sha256, "workflow manifest SHA-256")
    return _canonical_json(
        {
            "candidate_source_commit": candidate_source_sha,
            "repository": EXPECTED_REPOSITORY,
            "schema_version": SCHEMA_VERSION,
            "version": EXPECTED_VERSION,
            "workflow_manifest_sha256": manifest_sha256,
        }
    )


def publication_marker(
    *,
    candidate_source_sha: str,
    candidate_marker_sha: str,
    manifest_sha256: str,
) -> bytes:
    _require_sha(candidate_source_sha, "candidate source SHA")
    _require_sha(candidate_marker_sha, "candidate marker SHA")
    _require_digest(manifest_sha256, "workflow manifest SHA-256")
    return _canonical_json(
        {
            "candidate_marker_commit": candidate_marker_sha,
            "candidate_source_commit": candidate_source_sha,
            "repository": EXPECTED_REPOSITORY,
            "schema_version": SCHEMA_VERSION,
            "version": EXPECTED_VERSION,
            "workflow_manifest_sha256": manifest_sha256,
        }
    )


def _require_sha(value: str, subject: str) -> None:
    _require(bool(SHA_RE.fullmatch(value)), f"{subject} must be 40 lowercase hexadecimal digits")


def _require_digest(value: str, subject: str) -> None:
    _require(bool(re.fullmatch(r"[0-9a-f]{64}", value)), f"{subject} must be 64 lowercase hex digits")


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = exc.stderr
            if isinstance(stderr, bytes):
                detail = stderr.decode("utf-8", errors="replace").strip()
            elif stderr:
                detail = stderr.strip()
        suffix = f": {detail}" if detail else ""
        raise PublicationChainError(f"git {' '.join(args)} failed{suffix}") from exc
    return completed.stdout


def _commit_sha(root: Path, revision: str, subject: str) -> str:
    value = str(_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")).strip()
    _require_sha(value, subject)
    return value


def _parents(root: Path, revision: str) -> tuple[str, ...]:
    line = str(_git(root, "show", "-s", "--format=%P", revision)).strip()
    parents = tuple(line.split()) if line else ()
    for parent in parents:
        _require_sha(parent, f"parent of {revision}")
    return parents


def _blob(root: Path, revision: str, path: PurePosixPath) -> bytes:
    value = _git(root, "show", f"{revision}:{path.as_posix()}", text=False)
    assert isinstance(value, bytes)
    return value


def _single_added_path(root: Path, parent: str, child: str) -> str:
    output = str(
        _git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "--no-renames",
            "-r",
            parent,
            child,
        )
    )
    changes = [line for line in output.splitlines() if line]
    _require(len(changes) == 1, f"{child} must be a marker-only commit; changes: {changes!r}")
    fields = changes[0].split("\t")
    _require(
        len(fields) == 2 and fields[0] == "A",
        f"{child} must add exactly one marker file; change: {changes[0]!r}",
    )
    return fields[1]


def _marker_inventory(root: Path, revision: str) -> tuple[str, ...]:
    output = str(
        _git(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            revision,
            "--",
            MARKER_ROOT.as_posix(),
        )
    )
    return tuple(sorted(line for line in output.splitlines() if line))


def _manifest_digest(root: Path, candidate_sha: str) -> str:
    data = _blob(root, candidate_sha, MANIFEST_PATH)
    _require(bool(data), f"workflow manifest is empty at {candidate_sha}")
    return hashlib.sha256(data).hexdigest()


def verify_chain(root: Path, publication_revision: str) -> PublicationChain:
    root = root.resolve()
    _require((root / ".git").exists(), f"not a Git worktree: {root}")
    publication_sha = _commit_sha(root, publication_revision, "publication SHA")

    publication_parents = _parents(root, publication_sha)
    _require(
        len(publication_parents) == 1,
        "publication marker commit must have exactly one parent",
    )
    candidate_marker_sha = publication_parents[0]

    candidate_marker_parents = _parents(root, candidate_marker_sha)
    _require(
        len(candidate_marker_parents) == 1,
        "candidate marker commit must have exactly one parent",
    )
    candidate_source_sha = candidate_marker_parents[0]

    _require(
        _marker_inventory(root, candidate_source_sha) == (),
        f"candidate source must not contain {MARKER_ROOT.as_posix()}",
    )

    candidate_change = _single_added_path(root, candidate_source_sha, candidate_marker_sha)
    _require(
        candidate_change == CANDIDATE_MARKER_PATH.as_posix(),
        f"candidate marker commit must add only {CANDIDATE_MARKER_PATH.as_posix()}",
    )
    _require(
        _marker_inventory(root, candidate_marker_sha)
        == (CANDIDATE_MARKER_PATH.as_posix(),),
        "candidate marker commit has an unexpected publication-control inventory",
    )
    publication_change = _single_added_path(root, candidate_marker_sha, publication_sha)
    _require(
        publication_change == PUBLICATION_MARKER_PATH.as_posix(),
        f"publication marker commit must add only {PUBLICATION_MARKER_PATH.as_posix()}",
    )
    _require(
        _marker_inventory(root, publication_sha)
        == tuple(
            sorted(
                (
                    CANDIDATE_MARKER_PATH.as_posix(),
                    PUBLICATION_MARKER_PATH.as_posix(),
                )
            )
        ),
        "publication marker commit has an unexpected publication-control inventory",
    )

    manifest_sha256 = _manifest_digest(root, candidate_source_sha)
    expected_candidate = candidate_marker(
        candidate_source_sha=candidate_source_sha,
        manifest_sha256=manifest_sha256,
    )
    actual_candidate = _blob(root, candidate_marker_sha, CANDIDATE_MARKER_PATH)
    _require(
        actual_candidate == expected_candidate,
        f"{CANDIDATE_MARKER_PATH.as_posix()} is not the deterministic expected JSON",
    )

    expected_publication = publication_marker(
        candidate_source_sha=candidate_source_sha,
        candidate_marker_sha=candidate_marker_sha,
        manifest_sha256=manifest_sha256,
    )
    actual_publication = _blob(root, publication_sha, PUBLICATION_MARKER_PATH)
    _require(
        actual_publication == expected_publication,
        f"{PUBLICATION_MARKER_PATH.as_posix()} is not the deterministic expected JSON",
    )

    return PublicationChain(
        candidate_source_sha=candidate_source_sha,
        candidate_marker_sha=candidate_marker_sha,
        publication_sha=publication_sha,
        workflow_manifest_sha256=manifest_sha256,
    )


def verify_tag(root: Path, publication_sha: str, *, policy: str) -> None:
    _require(
        policy in {"ignore", "absent-or-publication", "publication"},
        f"unsupported tag policy: {policy}",
    )
    if policy == "ignore":
        return
    exists = subprocess.run(
        ["git", "-C", str(root), "show-ref", "--verify", "--quiet", f"refs/tags/{EXPECTED_TAG}"],
        check=False,
    ).returncode
    _require(exists in {0, 1}, f"could not inspect local tag {EXPECTED_TAG}")
    if exists == 1:
        _require(policy == "absent-or-publication", f"required tag {EXPECTED_TAG} is missing")
        return
    tag_sha = _commit_sha(root, f"refs/tags/{EXPECTED_TAG}", f"{EXPECTED_TAG} target")
    _require(tag_sha == publication_sha, f"{EXPECTED_TAG} must point to publication commit {publication_sha}")


def _write_github_output(path: Path, chain: PublicationChain) -> None:
    values = {
        "candidate_source_sha": chain.candidate_source_sha,
        "candidate_marker_sha": chain.candidate_marker_sha,
        "publication_sha": chain.publication_sha,
        "workflow_manifest_sha256": chain.workflow_manifest_sha256,
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the immutable two-marker SwirEngine 2.2 publication chain.",
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


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        chain = verify_chain(args.root, args.publication_sha)
        verify_tag(args.root, chain.publication_sha, policy=args.tag_policy)
        if args.github_output is not None:
            _write_github_output(args.github_output, chain)
    except (OSError, PublicationChainError) as exc:
        print(f"Publication chain verification FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "Publication chain PASS: "
        f"{chain.candidate_source_sha} -> {chain.candidate_marker_sha} -> "
        f"{chain.publication_sha}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
