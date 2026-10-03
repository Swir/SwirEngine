from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from tools.release_evidence_2_2 import (
    CHECKSUMS_NAME,
    EXPECTED_DISTRIBUTIONS,
    PROVENANCE_NAME,
    ReleaseEvidenceError,
    build_provenance,
    logical_sdist_sha256,
    sha256_file,
    verify_evidence,
    write_evidence,
)

CANDIDATE_SOURCE = "1" * 40
CANDIDATE_MARKER = "2" * 40
PUBLICATION = "3" * 40


def _write_sdist(path: Path, *, mtime: int = 1, payload: bytes = b"source") -> None:
    root = "swirengine-2.2.0"
    with tarfile.open(path, mode="w:gz") as archive:
        directory = tarfile.TarInfo(root)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        directory.mtime = mtime
        archive.addfile(directory)

        content = tarfile.TarInfo(f"{root}/src/swirengine/__init__.py")
        content.size = len(payload)
        content.mode = 0o644
        content.mtime = mtime
        archive.addfile(content, io.BytesIO(payload))


def _write_release_inputs(root: Path) -> tuple[Path, Path]:
    dist = root / "dist"
    dist.mkdir(parents=True)
    (dist / "swirengine-2.2.0-py3-none-any.whl").write_bytes(b"portable")
    (dist / "swirengine-2.2.0-cp314-cp314-win_amd64.whl").write_bytes(b"native")
    _write_sdist(dist / "swirengine-2.2.0.tar.gz")
    manifest = root / "2.2-required-workflows.json"
    manifest.write_text('{"required_workflows":["CI"]}\n', encoding="utf-8")
    return dist, manifest


def _options(manifest: Path) -> dict[str, object]:
    sdist = manifest.parent / "dist" / "swirengine-2.2.0.tar.gz"
    return {
        "candidate_source_commit": CANDIDATE_SOURCE,
        "candidate_marker_commit": CANDIDATE_MARKER,
        "publication_commit": PUBLICATION,
        "workflow_manifest": manifest,
        "expected_workflow_manifest_sha256": sha256_file(manifest),
        "expected_logical_sdist_sha256": logical_sdist_sha256(sdist),
    }


def test_v2_evidence_is_deterministic_and_binds_release_chain(tmp_path: Path) -> None:
    dist, manifest = _write_release_inputs(tmp_path)

    write_evidence(dist, **_options(manifest))
    first_checksums = (dist / CHECKSUMS_NAME).read_bytes()
    first_provenance = (dist / PROVENANCE_NAME).read_bytes()
    write_evidence(dist, **_options(manifest))

    assert (dist / CHECKSUMS_NAME).read_bytes() == first_checksums
    assert (dist / PROVENANCE_NAME).read_bytes() == first_provenance
    assert verify_evidence(dist, **_options(manifest)) == []

    provenance = json.loads(first_provenance)
    assert provenance["schema"] == "swirengine-release-provenance-v2"
    assert provenance["package"] == "swirengine"
    assert provenance["version"] == "2.2.0"
    assert provenance["candidate_source_commit"] == CANDIDATE_SOURCE
    assert provenance["candidate_marker_commit"] == CANDIDATE_MARKER
    assert provenance["publication_commit"] == PUBLICATION
    assert len(provenance["workflow_manifest_sha256"]) == 64
    assert len(provenance["logical_sdist_sha256"]) == 64
    assert [item["name"] for item in provenance["artifacts"]] == sorted(
        EXPECTED_DISTRIBUTIONS
    )


def test_logical_sdist_digest_ignores_archive_timestamps(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_sdist(first, mtime=1)
    _write_sdist(second, mtime=99)

    assert first.read_bytes() != second.read_bytes()
    assert logical_sdist_sha256(first) == logical_sdist_sha256(second)


def test_logical_sdist_digest_detects_content_change(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_sdist(first, payload=b"source")
    _write_sdist(second, payload=b"changed")

    assert logical_sdist_sha256(first) != logical_sdist_sha256(second)


def test_expected_logical_digest_locks_publication_to_candidate(tmp_path: Path) -> None:
    dist, manifest = _write_release_inputs(tmp_path)
    options = _options(manifest)
    expected = options["expected_logical_sdist_sha256"]

    assert build_provenance(dist, **options)["logical_sdist_sha256"] == expected
    options["expected_logical_sdist_sha256"] = "f" * 64
    with pytest.raises(ReleaseEvidenceError, match="differs from the accepted candidate"):
        build_provenance(dist, **options)


def test_evidence_detects_artifact_and_manifest_tampering(tmp_path: Path) -> None:
    dist, manifest = _write_release_inputs(tmp_path)
    options = _options(manifest)
    write_evidence(dist, **options)

    (dist / "swirengine-2.2.0-py3-none-any.whl").write_bytes(b"tampered")
    errors = verify_evidence(dist, **options)
    assert "release provenance does not match exact artifacts and release chain" in errors
    assert "SHA256SUMS does not match exact candidate distributions" in errors

    (dist / "swirengine-2.2.0-py3-none-any.whl").write_bytes(b"portable")
    manifest.write_text('{"required_workflows":["different"]}\n', encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError, match="workflow manifest digest differs"):
        verify_evidence(dist, **options)


def test_evidence_requires_exactly_three_distributions(tmp_path: Path) -> None:
    dist, manifest = _write_release_inputs(tmp_path)
    (dist / "swirengine-2.2.0-extra.whl").write_bytes(b"extra")

    with pytest.raises(ReleaseEvidenceError, match="unexpected distributions"):
        build_provenance(dist, **_options(manifest))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_source_commit", "a" * 39),
        ("candidate_marker_commit", "A" * 40),
        ("publication_commit", "z" * 40),
    ],
)
def test_evidence_rejects_noncanonical_commit_identity(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    dist, manifest = _write_release_inputs(tmp_path)
    options = _options(manifest)
    options[field] = value

    with pytest.raises(ReleaseEvidenceError, match=field):
        build_provenance(dist, **options)


def test_evidence_requires_three_distinct_chain_commits(tmp_path: Path) -> None:
    dist, manifest = _write_release_inputs(tmp_path)
    options = _options(manifest)
    options["publication_commit"] = CANDIDATE_MARKER

    with pytest.raises(ReleaseEvidenceError, match="must be distinct"):
        build_provenance(dist, **options)
