from swirengine import ParticleEmitter2D, Sprite2D
from swirengine.graphics import batching
from swirengine.graphics.batching import SpriteBatch, build_render_runs
from swirengine.math.types import Color


def test_repeatable_render_runs_stream_without_outer_materialization(tmp_path):
    texture = tmp_path / "atlas.png"
    objects = [Sprite2D(texture, x=index) for index in range(512)]

    runs = build_render_runs(objects)

    assert runs._cache is None
    streamed = list(runs)
    assert runs._cache is None
    assert len(streamed) == 1
    assert isinstance(streamed[0], SpriteBatch)
    assert len(streamed[0].sprites) == 512


def test_one_shot_render_runs_keep_sequence_compatibility(tmp_path):
    texture = tmp_path / "atlas.png"
    sprites = [Sprite2D(texture, x=index) for index in range(4)]
    runs = build_render_runs(sprite for sprite in sprites)

    assert len(runs) == 1
    assert isinstance(runs[0], SpriteBatch)
    assert runs[0].sprites == tuple(sprites)
    assert list(runs) == [runs[0]]


def test_sprite_batch_state_key_is_reused_across_frames(tmp_path):
    texture = tmp_path / "atlas.png"
    sprite = Sprite2D(texture, layer=3, screen_space=True)
    batching._canonical_texture_key.cache_clear()
    batching._cached_sprite_batch_key.cache_clear()

    first = batching.sprite_batch_key(sprite)
    for _ in range(1000):
        assert batching.sprite_batch_key(sprite) is first

    path_info = batching._canonical_texture_key.cache_info()
    key_info = batching._cached_sprite_batch_key.cache_info()
    assert path_info.misses == 1
    assert path_info.hits == 1000
    assert key_info.misses == 1
    assert key_info.hits == 1000


def test_in_range_color_clamp_is_allocation_free_identity_path():
    color = Color(0.25, 0.5, 0.75, 1.0)

    for _ in range(1000):
        assert color.clamped() is color

    assert Color(-1.0, 0.5, 2.0, 3.0).clamped() == Color(0.0, 0.5, 1.0, 1.0)


def test_particle_range_preserves_reversed_range_behavior():
    forward = ParticleEmitter2D(seed=19, emitting=False)
    reversed_range = ParticleEmitter2D(seed=19, emitting=False)

    forward_samples = [forward._range((2.0, 7.0)) for _ in range(64)]
    reversed_samples = [reversed_range._range((7.0, 2.0)) for _ in range(64)]

    assert reversed_samples == forward_samples
