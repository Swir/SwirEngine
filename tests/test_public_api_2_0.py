from __future__ import annotations

from pathlib import Path

import pytest

import swirengine
from tools.verify_2_0_public_api import (
    FINAL_VERSION,
    PUBLIC_VERSION_FLOOR,
    baseline_ref_available,
    expected_candidate_version,
    export_digest,
    git_blob_sha,
    load_manifest,
    read_baseline_source,
    read_module_version,
    read_project_version,
    read_static_all,
    read_static_all_text,
    validate_source_version,
    verify,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "public_api_2_0.json"
INIT_PATH = ROOT / "src" / "swirengine" / "__init__.py"
REQUIRES_BASELINE = pytest.mark.skipif(
    not baseline_ref_available(ROOT),
    reason=(
        "published v1.5.0 tag is not present in this shallow checkout; "
        "dedicated Public API 2.0 CI fetches full history"
    ),
)


@REQUIRES_BASELINE
def test_contract_is_anchored_to_published_1_5_tag() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    baseline_bytes = read_baseline_source(manifest, root=ROOT)
    baseline_exports = read_static_all_text(
        baseline_bytes.decode("utf-8"),
        source=f"{manifest['baseline_ref']}:{manifest['baseline_path']}",
    )

    assert manifest["baseline_release"] == "1.5.0"
    assert manifest["baseline_ref"] == "v1.5.0"
    assert manifest["baseline_init_blob_sha"] == "91827f52808f49182ef4b84477ff0fed182889bd"
    assert git_blob_sha(baseline_bytes) == manifest["baseline_init_blob_sha"]
    assert len(baseline_exports) == manifest["baseline_root_export_count"] == 271
    assert export_digest(baseline_exports) == manifest["baseline_root_exports_sha256"]


@REQUIRES_BASELINE
def test_current_root_api_preserves_every_published_baseline_export() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    baseline = read_static_all_text(
        read_baseline_source(manifest, root=ROOT).decode("utf-8"),
        source="v1.5.0:src/swirengine/__init__.py",
    )
    current = read_static_all(INIT_PATH)

    assert not [name for name in baseline if name not in current]


@REQUIRES_BASELINE
def test_published_baseline_exports_resolve_from_current_package() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    baseline = read_static_all_text(
        read_baseline_source(manifest, root=ROOT).decode("utf-8"),
        source="v1.5.0:src/swirengine/__init__.py",
    )

    missing = [name for name in baseline if not hasattr(swirengine, name)]
    assert missing == []


def test_source_version_preserves_2_0_floor_after_milestone_10() -> None:
    roadmap = (ROOT / "ROADMAP_2_0.md").read_text(encoding="utf-8")
    phase_version = expected_candidate_version(roadmap)
    project_version = read_project_version(ROOT / "pyproject.toml")
    module_version = read_module_version(INIT_PATH)

    assert PUBLIC_VERSION_FLOOR == "1.5.0"
    assert FINAL_VERSION == "2.0.0"
    assert phase_version in {PUBLIC_VERSION_FLOOR, FINAL_VERSION}
    validate_source_version(roadmap, project_version, module_version)
    assert project_version == module_version == swirengine.__version__
    if phase_version == FINAL_VERSION:
        assert tuple(map(int, project_version.split("."))) >= (2, 0, 0)
    else:
        assert project_version == PUBLIC_VERSION_FLOOR


@REQUIRES_BASELINE
def test_verifier_reports_complete_m1_evidence() -> None:
    evidence = verify(ROOT)
    project_version = read_project_version(ROOT / "pyproject.toml")

    assert "baseline=1.5.0" in evidence
    assert "baseline-root-exports=271" in evidence
    assert any(item.startswith("additive-root-exports=") for item in evidence)
    assert f"project-version={project_version}" in evidence
    assert "migration-ledger=present" in evidence
