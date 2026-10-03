from __future__ import annotations

import gzip
import io
import json
import tarfile
from pathlib import Path

import pytest

from tools.candidate_evidence_2_2 import (
    CHECKSUMS_NAME,
    EXPECTED_DISTRIBUTIONS,
    PROVENANCE_NAME,
    CandidateEvidenceError,
    build_provenance,
    main,
    render_checksums,
    render_provenance,
    verify_evidence,
    write_evidence,
)

SOURCE_SHA = "a" * 40


def _sdist(path: Path, *, unsafe_name: str | None = None) -> None:
    entries = [
        ("swirengine-2.2.0", "directory", b"", 0o755),
        ("swirengine-2.2.0/src", "directory", b"", 0o755),
        ("swirengine-2.2.0/src/swirengine", "directory", b"", 0o755),
        (
            unsafe_name or "swirengine-2.2.0/src/swirengine/__init__.py",
            "file",
            b'__version__ = "2.2.0"\n',
            0o644,
        ),
        (
            "swirengine-2.2.0/pyproject.toml",
            "file",
            b'[project]\nname = "swirengine"\nversion = "2.2.0"\n',
            0o644,
        ),
    ]
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, kind, content, mode in entries:
            info = tarfile.TarInfo(name)
            info.mode = mode
            info.mtime = 123
            if kind == "directory":
                info.type = tarfile.DIRTYPE
                info.size = 0
                archive.addfile(info)
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))


def _candidate(tmp_path: Path) -> tuple[Path, Path]:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / EXPECTED_DISTRIBUTIONS[0]).write_bytes(b"windows-cp314-wheel")
    (dist / EXPECTED_DISTRIBUTIONS[1]).write_bytes(b"portable-wheel")
    _sdist(dist / EXPECTED_DISTRIBUTIONS[2])
    manifest = tmp_path / "required-workflows.json"
    manifest.write_text('{"schema_version":1,"repository":"Swir/SwirEngine"}\n', encoding="utf-8")
    return dist, manifest


def test_generate_and_verify_bind_exact_source_manifest_sdist_and_artifacts(
    tmp_path: Path,
) -> None:
    dist, manifest = _candidate(tmp_path)

    checksums_path, provenance_path = write_evidence(
        dist,
        source_sha=SOURCE_SHA,
        workflow_manifest=manifest,
    )
    provenance = build_provenance(
        dist,
        source_sha=SOURCE_SHA,
        workflow_manifest=manifest,
    )

    assert checksums_path.name == CHECKSUMS_NAME
    assert provenance_path.name == PROVENANCE_NAME
    assert checksums_path.read_bytes() == render_checksums(provenance)
    assert provenance_path.read_bytes() == render_provenance(provenance)
    assert json.loads(provenance_path.read_text(encoding="utf-8")) == provenance
    assert provenance["candidate_source_commit"] == SOURCE_SHA
    assert len(provenance["workflow_manifest_sha256"]) == 64
    assert len(provenance["logical_sdist_sha256"]) == 64
    assert [artifact["name"] for artifact in provenance["artifacts"]] == sorted(
        EXPECTED_DISTRIBUTIONS
    )
    assert verify_evidence(
        dist,
        source_sha=SOURCE_SHA,
        workflow_manifest=manifest,
    ) == []


@pytest.mark.parametrize("source_sha", ["A" * 40, "a" * 39, "g" * 40, "v2.2.0"])
def test_source_sha_must_be_exact_canonical_commit(
    tmp_path: Path,
    source_sha: str,
) -> None:
    dist, manifest = _candidate(tmp_path)

    with pytest.raises(CandidateEvidenceError, match="40 lowercase"):
        build_provenance(dist, source_sha=source_sha, workflow_manifest=manifest)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_distribution_inventory_is_exact(tmp_path: Path, mutation: str) -> None:
    dist, manifest = _candidate(tmp_path)
    if mutation == "missing":
        (dist / EXPECTED_DISTRIBUTIONS[0]).unlink()
    else:
        (dist / "swirengine-2.2.0-extra.whl").write_bytes(b"extra")

    with pytest.raises(CandidateEvidenceError, match="distributions"):
        build_provenance(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)


def test_verify_rejects_artifact_or_manifest_drift(tmp_path: Path) -> None:
    dist, manifest = _candidate(tmp_path)
    write_evidence(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)

    (dist / EXPECTED_DISTRIBUTIONS[1]).write_bytes(b"tampered-wheel")
    artifact_errors = verify_evidence(
        dist,
        source_sha=SOURCE_SHA,
        workflow_manifest=manifest,
    )
    assert any("checksum" in error for error in artifact_errors)
    assert any("provenance" in error for error in artifact_errors)

    write_evidence(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)
    manifest.write_text("{}\n", encoding="utf-8")
    manifest_errors = verify_evidence(
        dist,
        source_sha=SOURCE_SHA,
        workflow_manifest=manifest,
    )
    assert any("provenance" in error for error in manifest_errors)


def test_verify_requires_canonical_bytes(tmp_path: Path) -> None:
    dist, manifest = _candidate(tmp_path)
    write_evidence(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)
    provenance_path = dist / PROVENANCE_NAME
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    errors = verify_evidence(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)

    assert errors == [
        "candidate provenance is not canonical or does not match exact source/artifacts"
    ]


def test_unsafe_logical_sdist_fails_closed(tmp_path: Path) -> None:
    dist, manifest = _candidate(tmp_path)
    _sdist(
        dist / EXPECTED_DISTRIBUTIONS[2],
        unsafe_name="swirengine-2.2.0/.release/publish-2.2.0/candidate.json",
    )

    with pytest.raises(CandidateEvidenceError, match="unsafe candidate source distribution"):
        build_provenance(dist, source_sha=SOURCE_SHA, workflow_manifest=manifest)


def test_cli_generate_then_verify(tmp_path: Path) -> None:
    dist, manifest = _candidate(tmp_path)
    common = [
        "--dist-dir",
        str(dist),
        "--source-sha",
        SOURCE_SHA,
        "--workflow-manifest",
        str(manifest),
    ]

    assert main(["generate", *common]) == 0
    assert main(["verify", *common]) == 0

    (dist / CHECKSUMS_NAME).write_text("tampered\n", encoding="utf-8")
    assert main(["verify", *common]) == 1
