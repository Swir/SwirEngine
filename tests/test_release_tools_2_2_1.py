from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path

import pytest

import tools.candidate_evidence_2_2 as historical_candidate
import tools.reconcile_release_2_2 as historical_reconcile
import tools.release_evidence_2_2 as historical_release
import tools.verify_publication_chain_2_2 as historical_chain
from tools.candidate_evidence_2_2_1 import EXPECTED_DISTRIBUTIONS
from tools.candidate_evidence_2_2_1 import build_provenance as build_candidate_provenance
from tools.reconcile_release_2_2_1 import (
    ReleaseReconciliationError,
    ReleaseSnapshot,
    load_expected_release,
    reconcile_release,
)
from tools.release_evidence_2_2_1 import (
    logical_sdist_sha256,
    sha256_file,
    verify_evidence,
    write_evidence,
)
from tools.verify_publication_chain_2_2_1 import (
    CANDIDATE_MARKER_PATH,
    EXPECTED_TAG,
    MANIFEST_PATH,
    PUBLICATION_MARKER_PATH,
    candidate_marker,
    publication_marker,
    verify_chain,
    verify_tag,
)

CANDIDATE_SOURCE = "1" * 40
CANDIDATE_MARKER = "2" * 40
PUBLICATION = "3" * 40


def _sdist(path: Path) -> None:
    root = "swirengine-2.2.1"
    with tarfile.open(path, mode="w:gz") as archive:
        directory = tarfile.TarInfo(root)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        payload = b'__version__ = "2.2.1"\n'
        info = tarfile.TarInfo(f"{root}/src/swirengine/__init__.py")
        info.size = len(payload)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(payload))


def _release_inputs(root: Path) -> tuple[Path, Path, Path, Path]:
    dist = root / "dist"
    dist.mkdir(parents=True)
    (dist / EXPECTED_DISTRIBUTIONS[0]).write_bytes(b"native")
    (dist / EXPECTED_DISTRIBUTIONS[1]).write_bytes(b"portable")
    _sdist(dist / EXPECTED_DISTRIBUTIONS[2])
    manifest = root / "manifest.json"
    manifest.write_text('{"required_workflows":["CI"]}\n', encoding="utf-8")
    notes = root / "RELEASE_NOTES_2_2_1.md"
    notes.write_text("# SwirEngine 2.2.1 Release Notes\n\nExact notes.\n", encoding="utf-8")
    description = root / "PYPI_DESCRIPTION_2_2_1.md"
    description.write_text("# SwirEngine 2.2.1\n\nExact detailed description.\n", encoding="utf-8")
    return dist, manifest, notes, description


def _release_options(dist: Path, manifest: Path) -> dict[str, object]:
    return {
        "candidate_source_commit": CANDIDATE_SOURCE,
        "candidate_marker_commit": CANDIDATE_MARKER,
        "publication_commit": PUBLICATION,
        "workflow_manifest": manifest,
        "expected_workflow_manifest_sha256": sha256_file(manifest),
        "expected_logical_sdist_sha256": logical_sdist_sha256(
            dist / "swirengine-2.2.1.tar.gz"
        ),
    }


def _pypi(expected: object, description: str) -> dict[str, object]:
    distributions = expected.distributions  # type: ignore[attr-defined]
    return {
        "info": {
            "name": "swirengine",
            "version": "2.2.1",
            "description": description,
            "description_content_type": "text/markdown",
            "requires_python": ">=3.10,<3.15",
        },
        "urls": [
            {
                "filename": item.name,
                "digests": {"sha256": item.sha256},
                "size": item.size,
                "yanked": False,
            }
            for item in distributions
        ],
    }


def test_patch_adapters_do_not_mutate_historical_2_2_0_modules() -> None:
    assert historical_candidate.EXPECTED_VERSION == "2.2.0"
    assert historical_release.EXPECTED_VERSION == "2.2.0"
    assert historical_reconcile.TAG == "v2.2.0"
    assert historical_chain.EXPECTED_TAG == "v2.2.0"
    assert EXPECTED_TAG == "v2.2.1"


def test_candidate_and_release_evidence_bind_exact_2_2_1_artifacts(tmp_path: Path) -> None:
    dist, manifest, _, _ = _release_inputs(tmp_path)
    candidate = build_candidate_provenance(
        dist,
        source_sha=CANDIDATE_SOURCE,
        workflow_manifest=manifest,
    )
    assert candidate["version"] == "2.2.1"
    assert [item["name"] for item in candidate["artifacts"]] == sorted(
        EXPECTED_DISTRIBUTIONS
    )

    options = _release_options(dist, manifest)
    write_evidence(dist, **options)
    assert verify_evidence(dist, **options) == []

    (dist / "swirengine-2.2.1-py3-none-any.whl").write_bytes(b"tampered")
    errors = verify_evidence(dist, **options)
    assert "release provenance does not match exact artifacts and release chain" in errors


def test_reconciliation_requires_exact_long_description_metadata(tmp_path: Path) -> None:
    dist, manifest, notes, description = _release_inputs(tmp_path)
    write_evidence(dist, **_release_options(dist, manifest))
    expected = load_expected_release(
        dist,
        publication_commit=PUBLICATION,
        release_notes=notes,
        pypi_description=description,
    )
    plan = reconcile_release(
        expected,
        ReleaseSnapshot(
            pypi=_pypi(expected, description.read_text(encoding="utf-8")),
            tag=None,
            release=None,
        ),
    )
    assert plan.pypi_uploads == ()
    assert plan.create_tag is True

    wrong = _pypi(expected, "different description")
    with pytest.raises(ReleaseReconciliationError, match="description does not match"):
        reconcile_release(expected, ReleaseSnapshot(pypi=wrong, tag=None, release=None))

    wrong_type = _pypi(expected, description.read_text(encoding="utf-8"))
    wrong_type["info"]["description_content_type"] = "text/plain"  # type: ignore[index]
    with pytest.raises(ReleaseReconciliationError, match="description_content_type"):
        reconcile_release(expected, ReleaseSnapshot(pypi=wrong_type, tag=None, release=None))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "--all")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def test_exact_2_2_1_two_marker_chain_and_tag(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "2.2.1 test")
    _git(root, "config", "user.email", "2.2.1@example.invalid")
    manifest = b'{"schema_version":1,"repository":"Swir/SwirEngine"}\n'
    manifest_path = root / MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(manifest)
    (root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    candidate_sha = _commit(root, "candidate")
    manifest_digest = hashlib.sha256(manifest).hexdigest()

    candidate_path = root / CANDIDATE_MARKER_PATH
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(
        candidate_marker(
            candidate_source_sha=candidate_sha,
            manifest_sha256=manifest_digest,
        )
    )
    candidate_marker_sha = _commit(root, "candidate marker")
    publication_path = root / PUBLICATION_MARKER_PATH
    publication_path.write_bytes(
        publication_marker(
            candidate_source_sha=candidate_sha,
            candidate_marker_sha=candidate_marker_sha,
            manifest_sha256=manifest_digest,
        )
    )
    publication_sha = _commit(root, "publication marker")

    chain = verify_chain(root, publication_sha)
    assert chain.candidate_source_sha == candidate_sha
    assert chain.candidate_marker_sha == candidate_marker_sha
    assert chain.publication_sha == publication_sha
    verify_tag(root, publication_sha, policy="absent-or-publication")
    _git(root, "tag", EXPECTED_TAG, publication_sha)
    verify_tag(root, publication_sha, policy="publication")
