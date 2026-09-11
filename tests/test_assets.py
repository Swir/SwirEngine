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
