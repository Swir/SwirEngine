from __future__ import annotations

from pathlib import Path

import pytest

from tools.verify_2_0_public_api import (
    PUBLIC_VERSION_FLOOR,
    baseline_ref_available,
    export_digest,
    git_blob_sha,
    load_manifest,
    read_baseline_source,
    read_module_version,
    read_project_version,
    read_static_all,
    read_static_all_text,
    verify,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "public_api_2_0.json"
INIT_PATH = ROOT / "src" / "swirengine" / "__init__.py"
REQUIRES_BASELINE = pytest.mark.skipif(
    not baseline_ref_available(ROOT),
    reason="published v1.5.0 tag is not present in this shallow checkout; dedicated Public API 2.0 CI fetches full history",
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


def test_source_versions_remain_frozen_until_final_2_0_gate() -> None:
    assert PUBLIC_VERSION_FLOOR == "1.5.0"
    assert read_project_version(ROOT / "pyproject.toml") == PUBLIC_VERSION_FLOOR
    assert read_module_version(INIT_PATH) == PUBLIC_VERSION_FLOOR


@REQUIRES_BASELINE
def test_verifier_reports_complete_m1_evidence() -> None:
    evidence = verify(ROOT)
    assert "baseline=1.5.0" in evidence
    assert "baseline-root-exports=271" in evidence
    assert "additive-root-exports=0" in evidence
    assert "project-version=1.5.0" in evidence
    assert "migration-ledger=present" in evidence
