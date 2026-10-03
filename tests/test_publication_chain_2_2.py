from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from tools.verify_publication_chain_2_2 import (
    CANDIDATE_MARKER_PATH,
    EXPECTED_TAG,
    MANIFEST_PATH,
    PUBLICATION_MARKER_PATH,
    PublicationChainError,
    candidate_marker,
    publication_marker,
    verify_chain,
    verify_tag,
)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write(root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "--all")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _publication_chain(
    tmp_path: Path,
    *,
    candidate_control_file: bool = False,
) -> tuple[Path, str, str, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "Phase A test")
    _git(root, "config", "user.email", "phase-a@example.invalid")
    manifest = b'{"schema_version":1,"repository":"Swir/SwirEngine","required_workflows":[]}\n'
    _write(root, MANIFEST_PATH.as_posix(), manifest)
    _write(root, "payload.txt", b"candidate\n")
    if candidate_control_file:
        _write(root, ".release/publish-2.2.0/extra.txt", b"unexpected\n")
    candidate_sha = _commit(root, "candidate")
    manifest_digest = hashlib.sha256(manifest).hexdigest()

    _write(
        root,
        CANDIDATE_MARKER_PATH.as_posix(),
        candidate_marker(
            candidate_source_sha=candidate_sha,
            manifest_sha256=manifest_digest,
        ),
    )
    candidate_marker_sha = _commit(root, "candidate marker")
    _write(
        root,
        PUBLICATION_MARKER_PATH.as_posix(),
        publication_marker(
            candidate_source_sha=candidate_sha,
            candidate_marker_sha=candidate_marker_sha,
            manifest_sha256=manifest_digest,
        ),
    )
    publication_sha = _commit(root, "publication marker")
    return root, candidate_sha, candidate_marker_sha, publication_sha, manifest_digest


def test_exact_two_marker_chain_passes(tmp_path: Path) -> None:
    root, candidate_sha, candidate_marker_sha, publication_sha, manifest_digest = (
        _publication_chain(tmp_path)
    )

    chain = verify_chain(root, publication_sha)

    assert chain.candidate_source_sha == candidate_sha
    assert chain.candidate_marker_sha == candidate_marker_sha
    assert chain.publication_sha == publication_sha
    assert chain.workflow_manifest_sha256 == manifest_digest


def test_candidate_marker_commit_must_be_marker_only(tmp_path: Path) -> None:
    root, candidate_sha, _, _, manifest_digest = _publication_chain(tmp_path)
    _git(root, "checkout", "--detach", candidate_sha)
    _write(
        root,
        CANDIDATE_MARKER_PATH.as_posix(),
        candidate_marker(
            candidate_source_sha=candidate_sha,
            manifest_sha256=manifest_digest,
        ),
    )
    _write(root, "unexpected.txt", b"not marker-only\n")
    bad_marker_sha = _commit(root, "bad candidate marker")
    _write(
        root,
        PUBLICATION_MARKER_PATH.as_posix(),
        publication_marker(
            candidate_source_sha=candidate_sha,
            candidate_marker_sha=bad_marker_sha,
            manifest_sha256=manifest_digest,
        ),
    )
    bad_publication_sha = _commit(root, "publication marker")

    with pytest.raises(PublicationChainError, match="marker-only"):
        verify_chain(root, bad_publication_sha)


def test_candidate_source_must_not_preseed_publication_control_files(
    tmp_path: Path,
) -> None:
    root, _, _, publication_sha, _ = _publication_chain(
        tmp_path,
        candidate_control_file=True,
    )

    with pytest.raises(PublicationChainError, match="candidate source must not contain"):
        verify_chain(root, publication_sha)


def test_publication_marker_requires_byte_exact_deterministic_json(tmp_path: Path) -> None:
    root, _, candidate_marker_sha, publication_sha, _ = _publication_chain(tmp_path)
    _git(root, "checkout", "--detach", candidate_marker_sha)
    data = _git(root, "show", f"{publication_sha}:{PUBLICATION_MARKER_PATH.as_posix()}")
    _write(root, PUBLICATION_MARKER_PATH.as_posix(), (data + " \n").encode())
    bad_publication_sha = _commit(root, "non-canonical publication marker")

    with pytest.raises(PublicationChainError, match="deterministic expected JSON"):
        verify_chain(root, bad_publication_sha)


def test_marker_sha_binding_rejects_replayed_publication_body(tmp_path: Path) -> None:
    root, candidate_sha, candidate_marker_sha, publication_sha, _ = _publication_chain(tmp_path)
    original_publication = _git(
        root,
        "show",
        f"{publication_sha}:{PUBLICATION_MARKER_PATH.as_posix()}",
    ).encode() + b"\n"
    _git(root, "checkout", "--detach", candidate_sha)
    manifest = _git(root, "show", f"HEAD:{MANIFEST_PATH.as_posix()}").encode() + b"\n"
    manifest_digest = hashlib.sha256(manifest).hexdigest()
    _write(
        root,
        CANDIDATE_MARKER_PATH.as_posix(),
        candidate_marker(
            candidate_source_sha=candidate_sha,
            manifest_sha256=manifest_digest,
        ),
    )
    replay_target = _commit(root, "second candidate marker")
    assert replay_target != candidate_marker_sha
    _write(root, PUBLICATION_MARKER_PATH.as_posix(), original_publication)
    replay_publication = _commit(root, "replayed publication marker")

    with pytest.raises(PublicationChainError, match="deterministic expected JSON"):
        verify_chain(root, replay_publication)


def test_tag_must_resolve_to_exact_publication_commit(tmp_path: Path) -> None:
    root, candidate_sha, _, publication_sha, _ = _publication_chain(tmp_path)
    verify_tag(root, publication_sha, policy="absent-or-publication")

    _git(root, "tag", EXPECTED_TAG, candidate_sha)
    with pytest.raises(PublicationChainError, match="must point to publication commit"):
        verify_tag(root, publication_sha, policy="publication")

    _git(root, "tag", "--force", EXPECTED_TAG, publication_sha)
    verify_tag(root, publication_sha, policy="publication")


def test_required_tag_policy_rejects_missing_tag(tmp_path: Path) -> None:
    root, _, _, publication_sha, _ = _publication_chain(tmp_path)

    with pytest.raises(PublicationChainError, match="required tag v2.2.0 is missing"):
        verify_tag(root, publication_sha, policy="publication")
