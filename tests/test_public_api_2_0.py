from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verify_2_0_public_api import (
    PUBLIC_VERSION_FLOOR,
    load_manifest,
    read_project_version,
    read_static_all,
    verify,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "public_api_2_0.json"
EXPECTED_1_5_ROOT_EXPORTS = [
    "__version__",
    "run",
    "GameEngine",
    "GameLogic",
    "GameObject",
    "ECSWorld",
    "EntityHandle",
    "System",
    "Transform2D",
    "Transform3D",
    "Velocity2D",
    "Velocity3D",
    "Lifetime",
    "ECSStats",
    "Time",
]


def test_contract_matches_published_1_5_root_api_floor() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    assert manifest["baseline_release"] == "1.5.0"
    assert manifest["baseline_ref"] == "v1.5.0"
    assert manifest["documented_root_exports"] == EXPECTED_1_5_ROOT_EXPORTS
    assert read_static_all(ROOT / "src" / "swirengine" / "__init__.py") == EXPECTED_1_5_ROOT_EXPORTS


def test_source_version_remains_frozen_until_final_2_0_gate() -> None:
    assert PUBLIC_VERSION_FLOOR == "1.5.0"
    assert read_project_version(ROOT / "pyproject.toml") == PUBLIC_VERSION_FLOOR


def test_verifier_reports_complete_m1_evidence() -> None:
    evidence = verify(ROOT)
    assert "baseline=1.5.0" in evidence
    assert "root-exports=15" in evidence
    assert "project-version=1.5.0" in evidence
    assert "migration-ledger=present" in evidence


def test_contract_rejects_duplicate_documented_exports(tmp_path: Path) -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["documented_root_exports"].append(data["documented_root_exports"][0])
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicates"):
        load_manifest(contract)


def test_contract_classifies_each_export_once() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    classified = [*manifest["stable_behavior_exports"], *manifest["compatibility_exports"]]
    assert sorted(classified) == sorted(EXPECTED_1_5_ROOT_EXPORTS)
    assert len(classified) == len(set(classified))
