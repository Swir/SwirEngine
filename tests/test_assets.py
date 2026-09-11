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
