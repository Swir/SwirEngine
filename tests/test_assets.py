from pathlib import Path

import pytest

from swirengine import AssetManager


def test_asset_manager_resolves_relative_paths(tmp_path):
    assets = AssetManager(tmp_path)
    assert assets.resolve("player.png") == tmp_path / "player.png"


def test_asset_alias_and_require(tmp_path):
    image = tmp_path / "hero.png"
    image.write_bytes(b"image")
    assets = AssetManager(tmp_path)
    assets.register("hero", "hero.png")

    assert assets.resolve("hero") == image
    assert assets.require("hero") == image
    assert assets.exists("hero")
    assert assets.unregister("hero") is True
    assert assets.unregister("hero") is False


def test_asset_require_raises_for_missing_file(tmp_path):
    assets = AssetManager(tmp_path)
    with pytest.raises(FileNotFoundError):
        assets.require(Path("missing.png"))


def test_asset_scan_is_deterministic_and_reports_sizes(tmp_path):
    (tmp_path / "textures").mkdir()
    (tmp_path / "textures" / "b.PNG").write_bytes(b"1234")
    (tmp_path / "a.wav").write_bytes(b"12")
    assets = AssetManager(tmp_path)

    files = assets.scan()
    assert [item.relative_path.as_posix() for item in files] == ["a.wav", "textures/b.PNG"]
    assert [item.size_bytes for item in files] == [2, 4]
    assert files[1].suffix == ".png"


def test_asset_diagnostics_detects_missing_aliases_and_groups_suffixes(tmp_path):
    (tmp_path / "hero.png").write_bytes(b"img")
    assets = AssetManager(tmp_path)
    assets.register("hero", "hero.png")
    assets.register("missing", "missing.wav")

    report = assets.diagnostics()
    assert report.file_count == 1
    assert report.total_bytes == 3
    assert report.healthy is False
    assert report.missing_aliases == ("missing",)
    assert len(report.by_suffix("png")) == 1
    assert len(report.by_suffix(".wav")) == 0


def test_asset_scan_handles_missing_root_and_rejects_file_root(tmp_path):
    assert AssetManager(tmp_path / "missing").scan() == ()

    file_root = tmp_path / "not-a-directory"
    file_root.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        AssetManager(file_root).scan()


def test_asset_loader_cache_is_shared_between_alias_and_path(tmp_path):
    path = tmp_path / "config.txt"
    path.write_text("alpha", encoding="utf-8")
    calls = []
    assets = AssetManager(tmp_path)
    assets.register("config", "config.txt")
    assets.register_loader("txt", lambda item: calls.append(item) or item.read_text(encoding="utf-8"))

    first = assets.load("config")
    second = assets.load(path)

    assert first == "alpha"
    assert second is first
    assert calls == [path.resolve()]
    assert assets.cached("config")
    assert assets.cached_paths() == (path.resolve(),)


def test_asset_invalidation_notifies_runtime_caches(tmp_path):
    path = tmp_path / "texture.bin"
    path.write_bytes(b"v1")
    invalidated = []
    assets = AssetManager(tmp_path)
    assets.register_loader(".bin", Path.read_bytes)
    assets.add_invalidator(invalidated.append)
    assets.load(path)

    assert assets.invalidate(path) is True
    assert assets.invalidate(path) is False
    assert invalidated == [path.resolve(), path.resolve()]


def test_live_asset_reload_replaces_cached_value(tmp_path):
    path = tmp_path / "level.txt"
    path.write_text("one", encoding="utf-8")
    assets = AssetManager(tmp_path)
    assets.register("level", "level.txt")
    assets.register_loader("txt", lambda item: item.read_text(encoding="utf-8"))
    assets.watch("level")
    assert assets.load("level") == "one"

    path.write_text("updated-level", encoding="utf-8")
    results = assets.poll_changes()

    assert len(results) == 1
    result = results[0]
    assert result.kind == "modified"
    assert result.aliases == ("level",)
    assert result.was_cached is True
    assert result.reloaded is True
    assert result.error is None
    assert assets.load("level") == "updated-level"


def test_live_asset_reload_invalidates_deleted_file(tmp_path):
    path = tmp_path / "gone.txt"
    path.write_text("value", encoding="utf-8")
    invalidated = []
    assets = AssetManager(tmp_path)
    assets.register_loader("txt", lambda item: item.read_text(encoding="utf-8"))
    assets.add_invalidator(invalidated.append)
    assets.watch(path)
    assets.load(path)

    path.unlink()
    result = assets.poll_changes()[0]

    assert result.kind == "deleted"
    assert result.was_cached is True
    assert result.reloaded is False
    assert assets.cached(path) is False
    assert invalidated == [path.resolve()]


def test_live_asset_reload_reports_loader_failure_without_poisoning_cache(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("ok", encoding="utf-8")
    assets = AssetManager(tmp_path)

    def loader(item):
        value = item.read_text(encoding="utf-8")
        if value == "bad-data":
            raise ValueError("bad asset")
        return value

    assets.register_loader("txt", loader)
    assets.watch(path)
    assert assets.load(path) == "ok"

    path.write_text("bad-data", encoding="utf-8")
    result = assets.poll_changes()[0]

    assert result.was_cached is True
    assert result.reloaded is False
    assert result.error == "bad asset"
    assert assets.cached(path) is False


def test_watch_cached_and_clear_cache_are_deterministic(tmp_path):
    a = tmp_path / "b.txt"
    b = tmp_path / "a.txt"
    a.write_text("b", encoding="utf-8")
    b.write_text("a", encoding="utf-8")
    assets = AssetManager(tmp_path)
    assets.register_loader("txt", lambda item: item.read_text(encoding="utf-8"))
    assets.load(a)
    assets.load(b)

    assert assets.cached_paths() == (b.resolve(), a.resolve())
    watched = assets.watch_cached()
    assert set(watched) == {a.resolve(), b.resolve()}
    assert assets.clear_cache() == 2
    assert assets.cached_paths() == ()
