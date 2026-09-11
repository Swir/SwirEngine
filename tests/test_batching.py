from swirengine import Rectangle2D, Sprite2D
from swirengine.graphics.batching import SpriteBatch, build_render_runs


def test_adjacent_compatible_sprites_share_one_batch(tmp_path):
    texture = tmp_path / "atlas.png"
    first = Sprite2D(texture, x=1)
    second = Sprite2D(texture, x=2)

    runs = build_render_runs((first, second))

    assert len(runs) == 1
    assert isinstance(runs[0], SpriteBatch)
    assert runs[0].sprites == (first, second)


def test_non_sprite_preserves_order_and_breaks_batch(tmp_path):
    texture = tmp_path / "atlas.png"
    first = Sprite2D(texture)
    marker = Rectangle2D(0, 0, 10, 10)
    second = Sprite2D(texture)

    runs = build_render_runs((first, marker, second))

    assert len(runs) == 3
    assert isinstance(runs[0], SpriteBatch)
    assert runs[1] is marker
    assert isinstance(runs[2], SpriteBatch)


def test_screen_space_or_layer_changes_break_batch(tmp_path):
    texture = tmp_path / "atlas.png"
    world = Sprite2D(texture, layer=0)
    hud = Sprite2D(texture, layer=0, screen_space=True)
    upper = Sprite2D(texture, layer=1)

    runs = build_render_runs((world, hud, upper))

    assert len(runs) == 3
    assert all(isinstance(run, SpriteBatch) for run in runs)


def test_hidden_objects_are_removed_before_batching(tmp_path):
    texture = tmp_path / "atlas.png"
    first = Sprite2D(texture)
    hidden = Sprite2D(texture, visible=False)
    second = Sprite2D(texture)

    runs = build_render_runs((first, hidden, second))

    assert len(runs) == 1
    assert isinstance(runs[0], SpriteBatch)
    assert runs[0].sprites == (first, second)


def test_non_renderable_scene_objects_are_ignored(tmp_path):
    texture = tmp_path / "atlas.png"
    sprite = Sprite2D(texture)
    marker = object()

    runs = build_render_runs((marker, sprite))

    assert len(runs) == 1
    assert isinstance(runs[0], SpriteBatch)
    assert runs[0].sprites == (sprite,)
