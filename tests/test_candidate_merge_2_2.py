from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tools.verify_candidate_merge_2_2 import (
    EXPECTED_REPOSITORY,
    CandidateMergeError,
    main,
    verify_candidate_merge,
)


@dataclass(frozen=True, slots=True)
class GitGraph:
    root: Path
    initial_sha: str
    candidate_sha: str
    merge_sha: str


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "--all")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _graph(tmp_path: Path) -> GitGraph:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Candidate merge test")
    _git(root, "config", "user.email", "candidate-merge@example.invalid")

    (root / "base.txt").write_text("base\n", encoding="utf-8")
    initial_sha = _commit(root, "base")

    _git(root, "switch", "-c", "candidate")
    (root / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    candidate_sha = _commit(root, "candidate")

    _git(root, "switch", "main")
    _git(root, "merge", "--no-ff", "candidate", "-m", "merge candidate")
    merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", merge_sha)
    return GitGraph(root, initial_sha, candidate_sha, merge_sha)


def _pull(
    graph: GitGraph,
    *,
    head_sha: str | None = None,
    merge_sha: str | None = None,
    head_repository: str = EXPECTED_REPOSITORY,
    base_repository: str = EXPECTED_REPOSITORY,
    base_ref: str = "main",
    merged_at: object = "2026-10-04T00:00:00Z",
) -> dict[str, object]:
    return {
        "number": 240,
        "head": {
            "sha": graph.candidate_sha if head_sha is None else head_sha,
            "repo": {"full_name": head_repository},
        },
        "base": {
            "ref": base_ref,
            "repo": {"full_name": base_repository},
        },
        "merged_at": merged_at,
        "merge_commit_sha": graph.merge_sha if merge_sha is None else merge_sha,
    }


def test_exact_same_repository_merge_on_fresh_main_passes(tmp_path: Path) -> None:
    graph = _graph(tmp_path)

    result = verify_candidate_merge(
        [_pull(graph)],
        candidate_sha=graph.candidate_sha,
        root=graph.root,
    )

    assert result.candidate_sha == graph.candidate_sha
    assert result.merge_commit_sha == graph.merge_sha
    assert result.main_sha == graph.merge_sha


def test_cli_writes_only_canonical_merge_sha_to_github_output(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    pulls_path = tmp_path / "pulls.json"
    output_path = tmp_path / "github-output.txt"
    pulls_path.write_text(json.dumps([_pull(graph)]), encoding="utf-8")

    exit_code = main(
        [
            "--pulls-json",
            str(pulls_path),
            "--candidate-sha",
            graph.candidate_sha,
            "--root",
            str(graph.root),
            "--github-output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8") == (
        f"merge_commit_sha={graph.merge_sha}\n"
    )


def test_stale_pull_head_is_rejected(tmp_path: Path) -> None:
    graph = _graph(tmp_path)

    with pytest.raises(CandidateMergeError, match="head SHA must be exact candidate"):
        verify_candidate_merge(
            [_pull(graph, head_sha=graph.initial_sha)],
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )


def test_unmerged_pull_is_rejected(tmp_path: Path) -> None:
    graph = _graph(tmp_path)

    with pytest.raises(CandidateMergeError, match="must be merged"):
        verify_candidate_merge(
            [_pull(graph, merged_at=None)],
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )


@pytest.mark.parametrize("side", ["head", "base"])
def test_fork_pull_is_rejected(tmp_path: Path, side: str) -> None:
    graph = _graph(tmp_path)
    overrides = {f"{side}_repository": "attacker/SwirEngine"}

    with pytest.raises(CandidateMergeError, match=r"repo\.full_name must be exactly"):
        verify_candidate_merge(
            [_pull(graph, **overrides)],
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )


@pytest.mark.parametrize("count", [0, 2])
def test_ambiguous_or_missing_pull_is_rejected(tmp_path: Path, count: int) -> None:
    graph = _graph(tmp_path)
    payload = [_pull(graph) for _ in range(count)]

    with pytest.raises(CandidateMergeError, match="exactly one pull request"):
        verify_candidate_merge(
            payload,
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )


def test_squash_merge_that_does_not_contain_candidate_is_rejected(tmp_path: Path) -> None:
    graph = _graph(tmp_path)

    with pytest.raises(CandidateMergeError, match="candidate source is not an ancestor"):
        verify_candidate_merge(
            [_pull(graph, merge_sha=graph.initial_sha)],
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )


def test_merge_not_reachable_from_fresh_main_is_rejected(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    _git(graph.root, "update-ref", "refs/remotes/origin/main", graph.initial_sha)

    with pytest.raises(CandidateMergeError, match="not an ancestor of fresh main ref"):
        verify_candidate_merge(
            [_pull(graph)],
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"base_ref": "release/2.2"}, "base.ref must be exactly main"),
        ({"merge_sha": "A" * 40}, "merge_commit_sha must be canonical"),
    ],
)
def test_pull_identity_must_be_canonical(
    tmp_path: Path,
    mutation: dict[str, str],
    message: str,
) -> None:
    graph = _graph(tmp_path)

    with pytest.raises(CandidateMergeError, match=message):
        verify_candidate_merge(
            [_pull(graph, **mutation)],
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )


def test_missing_candidate_commit_is_rejected(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    missing_sha = "1" * 40

    with pytest.raises(CandidateMergeError, match="rev-parse"):
        verify_candidate_merge(
            [_pull(graph, head_sha=missing_sha)],
            candidate_sha=missing_sha,
            root=graph.root,
        )


def test_missing_merge_commit_is_rejected(tmp_path: Path) -> None:
    graph = _graph(tmp_path)

    with pytest.raises(CandidateMergeError, match="rev-parse"):
        verify_candidate_merge(
            [_pull(graph, merge_sha="2" * 40)],
            candidate_sha=graph.candidate_sha,
            root=graph.root,
        )
