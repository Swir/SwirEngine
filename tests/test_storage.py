import json

import pytest

from swirengine import SaveStore
from swirengine.storage import (
    MigrationRegistry,
    ProfileStore,
    SettingSpec,
    SettingsSchema,
    SettingsStore,
)


def test_save_store_round_trip_and_defaults(tmp_path):
    path = tmp_path / "profile" / "save.json"
    store = SaveStore(path, defaults={"volume": 0.8})
    store.set("score", 9001).set("name", "Świr").save()

    loaded = SaveStore(path, defaults={"volume": 0.5, "difficulty": "normal"})
    assert loaded["score"] == 9001
    assert loaded["name"] == "Świr"
    assert loaded["volume"] == 0.8
    assert loaded["difficulty"] == "normal"


def test_save_store_delete_clear_and_mapping_helpers(tmp_path):
    store = SaveStore(tmp_path / "save.json", defaults={"lives": 3}, autoload=False)
    store["score"] = 10
    store.update({"level": 2})
    assert "score" in store and len(store) == 3
    assert store.delete("score")
    assert not store.delete("missing")
    store.clear()
    assert store.as_dict() == {"lives": 3}
    store.clear(keep_defaults=False)
    assert store.as_dict() == {}


def test_save_store_writes_valid_json_atomically(tmp_path):
    path = tmp_path / "save.json"
    SaveStore(path, autoload=False).update({"a": 1, "nested": {"ok": True}}).save()
    assert json.loads(path.read_text(encoding="utf-8"))["nested"]["ok"] is True
    assert not tuple(path.parent.glob(".save.json.*.tmp"))


def test_save_store_rejects_invalid_json_and_non_object_root(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid save data JSON"):
        SaveStore(invalid)

    array = tmp_path / "array.json"
    array.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(TypeError, match="root"):
        SaveStore(array)


def _settings_schema():
    return SettingsSchema(
        {
            "volume": SettingSpec(0.8, (int, float), minimum=0.0, maximum=1.0),
            "difficulty": SettingSpec("normal", str, choices=("easy", "normal", "hard")),
            "fullscreen": SettingSpec(False, bool),
        }
    )


def test_settings_store_validates_types_ranges_choices_and_unknown_keys(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", _settings_schema(), autoload=False)
    store.set("volume", 0.25).set("difficulty", "hard").set("fullscreen", True)
    assert store.as_dict() == {"volume": 0.25, "difficulty": "hard", "fullscreen": True}

    with pytest.raises(ValueError, match="<= 1.0"):
        store.set("volume", 1.5)
    with pytest.raises(TypeError, match="volume"):
        store.set("volume", True)
    with pytest.raises(ValueError, match="one of"):
        store.set("difficulty", "nightmare")
    with pytest.raises(KeyError, match="unknown setting"):
        store.set("cheats", True)
    assert store.diagnostics.validation_failures == 4


def test_settings_store_round_trip_versioned_envelope_and_reset(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path, _settings_schema(), version=2, autoload=False)
    store.update({"volume": 0.4, "fullscreen": True}).save()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["format"] == "swirengine-settings"
    assert raw["version"] == 2
    assert raw["values"]["volume"] == 0.4
    assert not tuple(path.parent.glob(".settings.json.*.tmp"))

    loaded = SettingsStore(path, _settings_schema(), version=2)
    assert loaded["volume"] == 0.4
    assert loaded["fullscreen"] is True
    loaded.reset("volume")
    assert loaded["volume"] == 0.8
    loaded.reset()
    assert loaded.as_dict() == _settings_schema().defaults()
    assert loaded.diagnostics.loads == 1


def test_settings_store_applies_ordered_migrations_before_validation(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "format": "swirengine-settings",
                "version": 1,
                "values": {"master_volume": 50, "fullscreen": True},
            }
        ),
        encoding="utf-8",
    )
    migrations = MigrationRegistry()
    migrations.register(
        1,
        lambda values: {
            "volume": values.pop("master_volume") / 100.0,
            **values,
            "difficulty": "normal",
        },
    )
    migrations.register(2, lambda values: {**values, "difficulty": "hard"})

    loaded = SettingsStore(path, _settings_schema(), version=3, migrations=migrations)
    assert loaded.as_dict() == {"volume": 0.5, "difficulty": "hard", "fullscreen": True}
    assert loaded.diagnostics.migrations == 2


def test_settings_store_refuses_missing_migration_and_future_version(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"format": "swirengine-settings", "version": 1, "values": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing migration"):
        SettingsStore(path, _settings_schema(), version=2)

    path.write_text(
        json.dumps({"format": "swirengine-settings", "version": 99, "values": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="newer than supported"):
        SettingsStore(path, _settings_schema(), version=2)


def test_profile_store_separates_settings_and_slots_and_lists_slots(tmp_path):
    profile = ProfileStore(tmp_path / "game-data", "player-01")
    settings = profile.settings(_settings_schema(), autoload=False)
    settings.set("difficulty", "hard").save()
    profile.save_slot("slot-2", autoload=False).set("level", 8).save()
    profile.save_slot("autosave", autoload=False).set("level", 7).save()

    assert profile.paths.settings == tmp_path / "game-data/profiles/player-01/settings.json"
    assert profile.paths.save_slot("slot-2") == tmp_path / "game-data/profiles/player-01/saves/slot-2.json"
    assert profile.list_slots() == ("autosave", "slot-2")
    assert profile.save_slot("slot-2")["level"] == 8


def test_profile_store_rejects_path_traversal_tokens(tmp_path):
    with pytest.raises(ValueError, match="profile"):
        ProfileStore(tmp_path, "../escape")
    profile = ProfileStore(tmp_path)
    with pytest.raises(ValueError, match="save slot"):
        profile.save_slot("../../escape")
