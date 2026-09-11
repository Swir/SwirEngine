from swirengine import Game, Rectangle2D


def test_game_scene_shortcuts():
    game = Game("Test")
    player = Rectangle2D(0, 0, 10, 10, name="player")
    assert game.add(player) is player
    assert player in game.scene
    assert game.remove(player) is True
    assert player not in game.scene


def test_game_validates_mode():
    try:
        Game(mode="4d")
    except ValueError as exc:
        assert "mode" in str(exc)
    else:
        raise AssertionError("invalid mode should raise ValueError")
