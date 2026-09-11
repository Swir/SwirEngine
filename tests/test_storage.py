import json

import pytest

from swirengine import SaveStore


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
    assert not path.with_name(".save.json.tmp").exists()


def test_save_store_rejects_invalid_json_and_non_object_root(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid save data JSON"):
        SaveStore(invalid)

    array = tmp_path / "array.json"
    array.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(TypeError, match="root"):
        SaveStore(array)
