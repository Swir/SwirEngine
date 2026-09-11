from pathlib import Path

from swirengine import Game, Rectangle2D


def test_game_scene_shortcuts():
    game = Game("Test")
    player = Rectangle2D(0, 0, 10, 10, name="player")
    assert game.add(player) is player
    assert player in game.scene
    assert game.remove(player) is True
    assert player not in game.scene


def test_game_sprite_uses_asset_root(tmp_path):
    game = Game("Test", asset_root=tmp_path)
    sprite = game.sprite("player.png", width=32, height=32)

    assert sprite.texture == tmp_path / "player.png"
    assert sprite in game.scene


def test_game_collider_helper_and_remove_cleanup():
    game = Game("Test")
    player = game.add(Rectangle2D(0, 0, 10, 10))
    collider = game.collider(player)

    assert collider in game.collisions.colliders
    assert game.remove(player)
    assert collider not in game.collisions.colliders


def test_game_validates_mode():
    try:
        Game(mode="4d")
    except ValueError as exc:
        assert "mode" in str(exc)
    else:
        raise AssertionError("invalid mode should raise ValueError")


def test_game_default_asset_root():
    assert Game().assets.root == Path("assets")
