from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.asset_cache import DerivedAssetCache


def test_cache_digest_is_stable_and_path_safe(tmp_path: Path) -> None:
    cache = DerivedAssetCache(tmp_path / "cache")
    first = cache.path_for("mesh", "../../outside/model.gltf")
    second = cache.path_for("mesh", "../../outside/model.gltf")

    assert first == second
    assert first.is_relative_to(cache.root)
    assert first.parent.parent == cache.root
    assert first.suffix == ".bin"


def test_cache_round_trips_bytes_and_tracks_hits(tmp_path: Path) -> None:
    cache = DerivedAssetCache(tmp_path / "cache")

    assert cache.get_bytes("mesh", "missing") is None
    path = cache.put_bytes("mesh", "triangle", b"derived-data")
    assert path.is_file()
    assert cache.get_bytes("mesh", "triangle") == b"derived-data"

    diagnostics = cache.diagnostics
    assert diagnostics.entries == 1
    assert diagnostics.bytes_used == len(b"derived-data")
    assert diagnostics.hits == 1
    assert diagnostics.misses == 1
    assert diagnostics.writes == 1


def test_cache_json_is_deterministic_and_reopenable(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    first = DerivedAssetCache(root)
    first.put_json("manifest", "scene", {"z": 2, "name": "świat", "a": 1})

    second = DerivedAssetCache(root)
    assert second.get_json("manifest", "scene") == {"a": 1, "name": "świat", "z": 2}
    assert second.diagnostics.entries == 1


def test_cache_prunes_oldest_entry_by_count_budget(tmp_path: Path, monkeypatch) -> None:
    cache = DerivedAssetCache(tmp_path / "cache", max_entries=2, max_bytes=1024)
    cache.put_bytes("mesh", "one", b"1")
    one = cache.path_for("mesh", "one")
    cache.put_bytes("mesh", "two", b"2")
    two = cache.path_for("mesh", "two")

    monkeypatch.setattr(
        cache,
        "_entry_records",
        lambda: (
            (one, 1, 1),
            (two, 2, 1),
            (cache.path_for("mesh", "three"), 3, 1),
        ),
    )
    three = cache.path_for("mesh", "three")
    three.parent.mkdir(parents=True, exist_ok=True)
    three.write_bytes(b"3")

    removed = cache.prune()

    assert removed == 1
    assert one.exists() is False
    assert two.exists()
    assert three.exists()
    assert cache.diagnostics.evictions == 1


def test_cache_prunes_to_byte_budget(tmp_path: Path) -> None:
    cache = DerivedAssetCache(tmp_path / "cache", max_entries=10, max_bytes=8)
    cache.put_bytes("blob", "first", b"1234")
    cache.put_bytes("blob", "second", b"5678")
    cache.put_bytes("blob", "third", b"abcd")

    diagnostics = cache.diagnostics
    assert diagnostics.entries <= 2
    assert diagnostics.bytes_used <= 8
    assert diagnostics.evictions >= 1


def test_cache_rejects_single_artifact_larger_than_budget(tmp_path: Path) -> None:
    cache = DerivedAssetCache(tmp_path / "cache", max_bytes=4)
    with pytest.raises(ValueError, match="byte budget"):
        cache.put_bytes("blob", "too-large", b"12345")


def test_cache_remove_and_clear(tmp_path: Path) -> None:
    cache = DerivedAssetCache(tmp_path / "cache")
    cache.put_bytes("a", "one", b"1")
    cache.put_bytes("b", "two", b"2")

    assert cache.remove("a", "one") is True
    assert cache.remove("a", "one") is False
    assert cache.clear() == 1
    assert cache.diagnostics.entries == 0


def test_cache_validates_limits_and_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_entries"):
        DerivedAssetCache(tmp_path / "cache-a", max_entries=0)
    with pytest.raises(ValueError, match="max_bytes"):
        DerivedAssetCache(tmp_path / "cache-b", max_bytes=0)

    cache = DerivedAssetCache(tmp_path / "cache-c")
    with pytest.raises(ValueError, match="namespace"):
        cache.path_for("", "key")
    with pytest.raises(ValueError, match="key"):
        cache.path_for("mesh", "")
