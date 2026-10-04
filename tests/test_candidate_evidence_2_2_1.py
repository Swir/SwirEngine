from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from tools.candidate_evidence_2_2_1 import (
    DEFAULT_WORKFLOW_MANIFEST,
    EXPECTED_DISTRIBUTIONS,
    CandidateEvidenceError,
    build_provenance,
    verify_evidence,
    write_evidence,
)

SOURCE_SHA = "a" * 40


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / EXPECTED_DISTRIBUTIONS[0]).write_bytes(b"native")
    (dist / EXPECTED_DISTRIBUTIONS[1]).write_bytes(b"portable")
    with tarfile.open(dist / EXPECTED_DISTRIBUTIONS[2], mode="w:gz") as archive:
        payload = b'__version__ = "2.2.1"\n'
        info = tarfile.TarInfo("swirengine-2.2.1/src/swirengine/__init__.py")
        info.size = len(payload)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(payload))
    manifest = tmp_path / "required.json"
    manifest.write_text('{"required_workflows":["CI"]}\n', encoding="utf-8")
    return dist, manifest


def test_default_manifest_and_exact_distribution_names_are_patch_specific() -> None:
    assert DEFAULT_WORKFLOW_MANIFEST.as_posix().endswith(
        ".github/release-gates/2.2.1-required-workflows.json"
    )
    assert EXPECTED_DISTRIBUTIONS == (
        "swirengine-2.2.1-cp314-cp314-win_amd64.whl",
        "swirengine-2.2.1-py3-none-any.whl",
        "swirengine-2.2.1.tar.gz",
    )


def test_candidate_evidence_round_trip_is_exact(tmp_path: Path) -> None:
    dist, manifest = _inputs(tmp_path)
    provenance = build_provenance(
        dist,
        source_sha=SOURCE_SHA,
        workflow_manifest=manifest,
    )
    write_evidence(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)

    assert provenance["version"] == "2.2.1"
    assert provenance["candidate_source_commit"] == SOURCE_SHA
    assert verify_evidence(
        dist,
        source_sha=SOURCE_SHA,
        workflow_manifest=manifest,
    ) == []


def test_candidate_evidence_rejects_incomplete_or_extra_inventory(tmp_path: Path) -> None:
    dist, manifest = _inputs(tmp_path)
    (dist / EXPECTED_DISTRIBUTIONS[0]).unlink()
    with pytest.raises(CandidateEvidenceError, match="missing distributions"):
        build_provenance(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)

    (dist / EXPECTED_DISTRIBUTIONS[0]).write_bytes(b"native")
    (dist / "swirengine-2.2.1-extra.whl").write_bytes(b"extra")
    with pytest.raises(CandidateEvidenceError, match="unexpected distributions"):
        build_provenance(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)
