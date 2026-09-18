from __future__ import annotations

import json
from dataclasses import replace

import pytest

from tools.verify_api_contract_2_0 import (
    BASELINE_VERSION,
    TARGET_VERSION,
    ApiSurface,
    BaselineContract,
    ContractError,
    MigrationPlan,
    Removal,
    _canonical_exports_digest,
    audit,
    load_baseline,
    load_migration_plan,
    parse_api_surface,
    read_project_version,
    validate_contract,
)


def test_repository_api_contract_is_locked_to_released_1_5_baseline() -> None:
    baseline = load_baseline()
    surface = parse_api_surface()
    migration = load_migration_plan()
    report = audit()

    assert baseline.version == BASELINE_VERSION
    assert baseline.source_tag == "v1.5.0"
    assert len(baseline.exports) == 271
    assert baseline.digest == _canonical_exports_digest(baseline.exports)
    assert surface.version == BASELINE_VERSION
    assert set(surface.exports) == set(baseline.exports)
    assert migration.baseline_version == BASELINE_VERSION
    assert migration.target_version == TARGET_VERSION
    assert migration.graduated_exports == ()
    assert migration.removals == ()
    assert read_project_version() == BASELINE_VERSION
    assert report["current_export_count"] == 271
    assert report["graduated_export_count"] == 0
    assert report["documented_removal_count"] == 0
    assert report["mode"] == "source-development"


def test_undocumented_baseline_removal_is_rejected() -> None:
    baseline = BaselineContract("1.5.0", "v1.5.0", ("Game", "Scene"), _canonical_exports_digest(("Game", "Scene")))
    surface = ApiSurface("1.5.0", ("Game",), frozenset({"Game"}))
    migration = MigrationPlan("1.5.0", "2.0.0", (), ())

    with pytest.raises(ContractError, match="undocumented removals=Scene"):
        validate_contract(surface, baseline, migration, project_version="1.5.0")


def test_undocumented_new_root_export_is_rejected() -> None:
    baseline = BaselineContract("1.5.0", "v1.5.0", ("Game",), _canonical_exports_digest(("Game",)))
    surface = ApiSurface("1.5.0", ("Game", "NewThing"), frozenset({"Game", "NewThing"}))
    migration = MigrationPlan("1.5.0", "2.0.0", (), ())

    with pytest.raises(ContractError, match="undocumented root exports=NewThing"):
        validate_contract(surface, baseline, migration, project_version="1.5.0")


def test_explicit_graduation_and_documented_replacement_are_accepted() -> None:
    baseline = BaselineContract("1.5.0", "v1.5.0", ("OldThing",), _canonical_exports_digest(("OldThing",)))
    surface = ApiSurface("1.5.0", ("NewThing",), frozenset({"NewThing"}))
    migration = MigrationPlan(
        "1.5.0",
        "2.0.0",
        ("NewThing",),
        (Removal("OldThing", "NewThing", "Replace the legacy surface with the production API."),),
    )

    report = validate_contract(surface, baseline, migration, project_version="1.5.0")

    assert report["graduated_export_count"] == 1
    assert report["documented_removal_count"] == 1


def test_documented_replacement_must_be_public() -> None:
    baseline = BaselineContract("1.5.0", "v1.5.0", ("OldThing",), _canonical_exports_digest(("OldThing",)))
    surface = ApiSurface("1.5.0", (), frozenset())
    migration = MigrationPlan(
        "1.5.0",
        "2.0.0",
        (),
        (Removal("OldThing", "MissingThing", "Move callers to the replacement production surface."),),
    )

    with pytest.raises(ContractError, match="replacement 'MissingThing'.*is not public"):
        validate_contract(surface, baseline, migration, project_version="1.5.0")


def test_release_candidate_mode_requires_2_0_version_on_both_surfaces() -> None:
    baseline = BaselineContract("1.5.0", "v1.5.0", ("Game",), _canonical_exports_digest(("Game",)))
    development_surface = ApiSurface("1.5.0", ("Game",), frozenset({"Game"}))
    migration = MigrationPlan("1.5.0", "2.0.0", (), ())

    with pytest.raises(ContractError, match="expected=2.0.0"):
        validate_contract(
            development_surface,
            baseline,
            migration,
            project_version="1.5.0",
            release_candidate=True,
        )

    candidate_surface = replace(development_surface, version="2.0.0")
    report = validate_contract(
        candidate_surface,
        baseline,
        migration,
        project_version="2.0.0",
        release_candidate=True,
    )
    assert report["mode"] == "release-candidate"


def test_baseline_loader_rejects_tampered_count_or_digest(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package": "swirengine",
                "baseline_version": "1.5.0",
                "source_tag": "v1.5.0",
                "public_export_count": 2,
                "public_exports_sha256": "not-the-real-digest",
                "public_exports": ["Game"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="public_export_count"):
        load_baseline(path)


def test_static_surface_parser_rejects_unbound_public_name(tmp_path) -> None:
    init_path = tmp_path / "__init__.py"
    init_path.write_text('__all__ = ["Game", "Ghost"]\nGame = object()\n__version__ = "1.5.0"\n', encoding="utf-8")

    with pytest.raises(ContractError, match="unbound names: Ghost"):
        parse_api_surface(init_path)
