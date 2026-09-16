from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.storage import MigrationRegistry, ProfileStore
from swirengine.storage15 import (
    AutosavePolicy,
    ProfileSaveManager2,
    SaveIntegrityError,
    SaveRecoveryError,
    SaveSlotStore2,
)


def test_versioned_save_round_trip_records_integrity_revision_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    store = SaveSlotStore2(path)
    info = store.save(
        {"level": 7, "player": {"name": "Świr", "health": 90}},
        metadata={"title": "Checkpoint"},
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["format"] == "swirengine-save-slot"
    assert raw["format_version"] == 1
    assert raw["version"] == 1
    assert raw["revision"] == 1
    assert raw["integrity"]["algorithm"] == "sha256"
    assert len(raw["integrity"]["digest"]) == 64
    assert info.revision == 1
    assert info.metadata == {"title": "Checkpoint"}

    loaded = store.load()
    assert loaded.data["level"] == 7
    assert loaded.data["player"] == {"name": "Świr", "health": 90}
    assert loaded.metadata == {"title": "Checkpoint"}
    assert loaded.source == "primary"
    assert not loaded.recovered


def test_second_save_keeps_previous_primary_as_verified_backup(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    store.save({"score": 10})
    info = store.save({"score": 20})

    assert info.revision == 2
    assert store.backup_path.exists()
    assert store.load().data["score"] == 20

    store.path.unlink()
    backup = store.load()
    assert backup.data["score"] == 10
    assert backup.revision == 1
    assert backup.recovered


def test_tampered_primary_falls_back_to_valid_backup(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    store.save({"score": 1})
    store.save({"score": 2})
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["data"]["score"] = 999
    store.path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = store.load()
    assert loaded.data == {"score": 1}
    assert loaded.source == "backup"
    assert store.diagnostics.integrity_failures == 1
    assert store.diagnostics.recoveries == 1


def test_load_repair_restores_valid_primary_from_backup(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    store.save({"value": 1})
    store.save({"value": 2})
    store.path.write_text("{broken", encoding="utf-8")

    loaded = store.load(repair=True)
    assert loaded.data == {"value": 1}
    assert store.path.exists()
    assert SaveSlotStore2(store.path).load().data == {"value": 1}


def test_explicit_recover_restores_backup_bytes(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    store.save({"value": "old"})
    store.save({"value": "new"})
    backup_bytes = store.backup_path.read_bytes()
    store.path.write_text("invalid", encoding="utf-8")

    result = store.recover()
    assert result.data == {"value": "old"}
    assert store.path.read_bytes() == backup_bytes


def test_primary_and_backup_corruption_raise_recovery_error(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    store.save({"value": 1})
    store.save({"value": 2})
    store.path.write_text("broken", encoding="utf-8")
    store.backup_path.write_text("also broken", encoding="utf-8")

    with pytest.raises(SaveRecoveryError, match="primary and backup"):
        store.load()
    with pytest.raises(SaveRecoveryError, match="primary and backup"):
        store.save({"value": 3})


def test_corrupt_primary_without_backup_is_never_overwritten_silently(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    path.write_text("{bad", encoding="utf-8")
    store = SaveSlotStore2(path)

    with pytest.raises(SaveRecoveryError, match="no backup"):
        store.load()
    with pytest.raises(SaveRecoveryError, match="refusing to overwrite"):
        store.save({"safe": True})
    assert path.read_text(encoding="utf-8") == "{bad"


def test_missing_slot_raises_file_not_found(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        store.load()
    with pytest.raises(FileNotFoundError):
        store.recover()


def test_save_data_rejects_nonportable_values(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    with pytest.raises(ValueError, match="finite"):
        store.save({"bad": float("nan")})
    with pytest.raises(TypeError, match="keys"):
        store.save({"nested": {1: "bad"}})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="unsupported"):
        store.save({"object": object()})


def test_defaults_are_merged_without_being_persisted_as_missing_fields(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    SaveSlotStore2(path).save({"score": 7})
    loaded = SaveSlotStore2(path, defaults={"lives": 3, "score": 0}).load()
    assert loaded.data == {"lives": 3, "score": 7}

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["data"] == {"score": 7}


def test_future_save_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    SaveSlotStore2(path, version=3).save({"level": 1})
    with pytest.raises(SaveRecoveryError, match="no backup"):
        SaveSlotStore2(path, version=2).load()


def _migrations() -> MigrationRegistry:
    migrations = MigrationRegistry()
    migrations.register(
        1,
        lambda data: {"coins": data.pop("credits"), **data, "difficulty": "normal"},
    )
    migrations.register(2, lambda data: {**data, "difficulty": "hard"})
    return migrations


def test_ordered_save_migrations_apply_before_defaults(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    SaveSlotStore2(path, version=1).save({"credits": 40, "level": 3})

    loaded = SaveSlotStore2(
        path,
        version=3,
        migrations=_migrations(),
        defaults={"lives": 3},
    ).load()
    assert loaded.data == {"coins": 40, "difficulty": "hard", "level": 3, "lives": 3}
    assert loaded.stored_version == 1
    assert loaded.target_version == 3
    assert loaded.migrations_applied == 2
    assert loaded.migrated


def test_upgrade_persists_migrated_state_as_new_revision(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    SaveSlotStore2(path, version=1).save({"credits": 5})
    store = SaveSlotStore2(path, version=3, migrations=_migrations())

    result = store.load(upgrade=True)
    assert result.migrations_applied == 2

    persisted = SaveSlotStore2(path, version=3).load()
    assert persisted.data == {"coins": 5, "difficulty": "hard"}
    assert persisted.revision == 2
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 3


def test_missing_migration_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    SaveSlotStore2(path, version=1).save({"level": 1})
    with pytest.raises(SaveRecoveryError, match="no backup"):
        SaveSlotStore2(path, version=2).load()


def test_inspect_reports_healthy_slot_and_backup_availability(tmp_path: Path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    store.save({"value": 1}, metadata={"title": "First"})
    first = store.inspect(name="manual")
    assert first.healthy
    assert not first.recovery_available
    assert first.revision == 1
    assert first.metadata == {"title": "First"}

    store.save({"value": 2}, metadata={"title": "Second"})
    second = store.inspect(name="manual")
    assert second.healthy
    assert second.recovery_available
    assert second.revision == 2


def test_inspect_reports_corrupt_primary_as_recoverable_when_backup_is_valid(
    tmp_path: Path,
) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    store.save({"value": 1}, metadata={"title": "Old"})
    store.save({"value": 2}, metadata={"title": "New"})
    store.path.write_text("broken", encoding="utf-8")

    info = store.inspect(name="slot")
    assert not info.healthy
    assert info.recovery_available
    assert info.revision == 1
    assert info.metadata == {"title": "Old"}


def test_profile_manager_uses_additive_directory_without_touching_legacy_slots(
    tmp_path: Path,
) -> None:
    legacy = ProfileStore(tmp_path, "player-1")
    legacy.save_slot("manual", autoload=False).set("legacy", True).save()
    manager = ProfileSaveManager2(tmp_path, "player-1")
    manager.save("manual", {"modern": True})

    assert manager.slot_path("manual") == (
        tmp_path / "profiles/player-1/saves-v2/manual.json"
    )
    assert legacy.save_slot("manual").as_dict() == {"legacy": True}
    assert manager.load("manual").data == {"modern": True}


def test_profile_manager_lists_health_and_metadata_for_slots(tmp_path: Path) -> None:
    manager = ProfileSaveManager2(tmp_path)
    manager.save("slot-b", {"level": 2}, metadata={"title": "B"})
    manager.save("slot-a", {"level": 1}, metadata={"title": "A"})
    manager.save("slot-b", {"level": 3}, metadata={"title": "B2"})
    manager.slot("slot-b").path.write_text("broken", encoding="utf-8")

    infos = manager.list_slots()
    assert [info.name for info in infos] == ["slot-a", "slot-b"]
    assert infos[0].healthy
    assert not infos[1].healthy
    assert infos[1].recovery_available
    assert infos[1].metadata == {"title": "B"}


def test_profile_manager_delete_can_preserve_or_remove_backup(tmp_path: Path) -> None:
    manager = ProfileSaveManager2(tmp_path)
    manager.save("manual", {"value": 1})
    manager.save("manual", {"value": 2})
    store = manager.slot("manual")

    assert manager.delete("manual", include_backup=False)
    assert not store.path.exists()
    assert store.backup_path.exists()
    assert manager.load("manual").data == {"value": 1}

    assert manager.delete("manual")
    assert not store.path.exists()
    assert not store.backup_path.exists()
    assert not manager.delete("manual")


def test_import_legacy_copies_data_and_leaves_legacy_file_unchanged(tmp_path: Path) -> None:
    legacy = ProfileStore(tmp_path, "player")
    legacy.save_slot("slot-1", autoload=False).update({"level": 8, "score": 50}).save()
    legacy_bytes = legacy.paths.save_slot("slot-1").read_bytes()

    manager = ProfileSaveManager2(tmp_path, "player")
    info = manager.import_legacy("slot-1", metadata={"title": "Imported"})
    loaded = manager.load("slot-1")

    assert info.revision == 1
    assert loaded.data == {"level": 8, "score": 50}
    assert loaded.metadata == {"imported_from": "swirengine-1.x", "title": "Imported"}
    assert legacy.paths.save_slot("slot-1").read_bytes() == legacy_bytes


def test_import_missing_legacy_slot_is_rejected(tmp_path: Path) -> None:
    manager = ProfileSaveManager2(tmp_path)
    with pytest.raises(FileNotFoundError):
        manager.import_legacy("missing")


def test_autosave_rotates_bounded_slots_with_monotonic_generation(tmp_path: Path) -> None:
    manager = ProfileSaveManager2(tmp_path)
    policy = AutosavePolicy(keep=3, prefix="auto")

    for generation in range(1, 8):
        info = manager.autosave({"step": generation}, policy=policy)
        assert info.metadata is not None
        assert info.metadata["autosave_generation"] == generation
        assert info.metadata["autosave_index"] == ((generation - 1) % 3) + 1

    autosaves = manager.list_autosaves(policy=policy)
    assert [item.metadata["autosave_generation"] for item in autosaves if item.metadata] == [
        7,
        6,
        5,
    ]
    assert len(tuple(manager.directory.glob("auto-*.json"))) == 3


def test_autosave_preserves_caller_metadata_and_marks_slot(tmp_path: Path) -> None:
    manager = ProfileSaveManager2(tmp_path)
    info = manager.autosave({"level": 2}, metadata={"scene": "boss"})
    assert info.metadata == {
        "scene": "boss",
        "autosave": True,
        "autosave_generation": 1,
        "autosave_index": 1,
    }


def test_autosave_recovers_valid_backup_before_overwriting_corrupt_target(
    tmp_path: Path,
) -> None:
    manager = ProfileSaveManager2(tmp_path)
    policy = AutosavePolicy(keep=1)
    manager.autosave({"step": 1}, policy=policy)
    manager.autosave({"step": 2}, policy=policy)
    store = manager.slot("autosave-1")
    store.path.write_text("broken", encoding="utf-8")

    info = manager.autosave({"step": 3}, policy=policy)
    assert info.metadata is not None
    assert info.metadata["autosave_generation"] == 2
    assert manager.load("autosave-1").data == {"step": 3}


def test_profile_and_slot_tokens_reject_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="profile"):
        ProfileSaveManager2(tmp_path, "../escape")
    manager = ProfileSaveManager2(tmp_path)
    with pytest.raises(ValueError, match="save slot"):
        manager.slot("../../escape")
    with pytest.raises(ValueError, match="autosave prefix"):
        AutosavePolicy(prefix="../auto")


def test_autosave_policy_validates_bounds() -> None:
    with pytest.raises(ValueError, match="keep"):
        AutosavePolicy(keep=0)
    policy = AutosavePolicy(keep=2)
    with pytest.raises(ValueError, match="index"):
        policy.slot_name(0)
    with pytest.raises(ValueError, match="index"):
        policy.slot_name(3)


def test_diagnostics_record_real_save_load_recovery_and_migration_activity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "slot.json"
    SaveSlotStore2(path, version=1).save({"credits": 10})
    store = SaveSlotStore2(path, version=3, migrations=_migrations())
    migrated = store.load()
    assert migrated.migrations_applied == 2
    store.save(migrated.data)
    store.path.write_text("broken", encoding="utf-8")
    recovered = store.load()
    assert recovered.recovered

    diagnostics = store.diagnostics
    assert diagnostics.loads >= 2
    assert diagnostics.saves == 1
    assert diagnostics.recoveries >= 1
    assert diagnostics.migrations >= 2
