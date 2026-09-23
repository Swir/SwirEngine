from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.release_evidence_2_1 import (
    CHECKSUMS_NAME,
    PROVENANCE_NAME,
    build_provenance,
    verify_evidence,
    write_evidence,
)

SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _write_artifacts(dist: Path, *, include_native: bool = True) -> None:
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "swirengine-2.1.0-py3-none-any.whl").write_bytes(b"portable-wheel")
    (dist / "swirengine-2.1.0.tar.gz").write_bytes(b"source-distribution")
    if include_native:
        (dist / "swirengine-2.1.0-cp314-cp314-win_amd64.whl").write_bytes(
            b"windows-native-wheel"
        )


def test_release_evidence_is_deterministic_and_binds_exact_source(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_artifacts(dist)

    write_evidence(dist, SOURCE_SHA, require_windows_cp314=True)
    first_checksums = (dist / CHECKSUMS_NAME).read_bytes()
    first_provenance = (dist / PROVENANCE_NAME).read_bytes()

    write_evidence(dist, SOURCE_SHA, require_windows_cp314=True)

    assert (dist / CHECKSUMS_NAME).read_bytes() == first_checksums
    assert (dist / PROVENANCE_NAME).read_bytes() == first_provenance
    assert verify_evidence(dist, SOURCE_SHA, require_windows_cp314=True) == []

    provenance = json.loads(first_provenance)
    assert provenance["source_commit"] == SOURCE_SHA
    assert provenance["version"] == "2.1.0"
    assert [item["name"] for item in provenance["artifacts"]] == sorted(
        item["name"] for item in provenance["artifacts"]
    )


def test_release_evidence_detects_artifact_tampering(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_artifacts(dist)
    write_evidence(dist, SOURCE_SHA, require_windows_cp314=True)

    (dist / "swirengine-2.1.0.tar.gz").write_bytes(b"tampered")

    errors = verify_evidence(dist, SOURCE_SHA, require_windows_cp314=True)

    assert "release provenance does not match exact candidate artifacts/source" in errors
    assert "SHA256SUMS does not match exact candidate artifacts" in errors


def test_release_evidence_requires_windows_cp314_when_requested(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_artifacts(dist, include_native=False)

    with pytest.raises(ValueError, match="missing Windows CPython 3.14 wheel"):
        build_provenance(dist, SOURCE_SHA, require_windows_cp314=True)


@pytest.mark.parametrize("source_sha", ["abc", "g" * 40, "1" * 39])
def test_release_evidence_rejects_invalid_source_identity(
    tmp_path: Path, source_sha: str
) -> None:
    dist = tmp_path / "dist"
    _write_artifacts(dist)

    with pytest.raises(ValueError, match="source SHA must be exactly 40"):
        build_provenance(dist, source_sha, require_windows_cp314=True)


def test_release_evidence_detects_wrong_source_identity(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_artifacts(dist)
    write_evidence(dist, SOURCE_SHA, require_windows_cp314=True)

    errors = verify_evidence(dist, "a" * 40, require_windows_cp314=True)

    assert "release provenance does not match exact candidate artifacts/source" in errors
