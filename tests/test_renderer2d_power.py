from types import SimpleNamespace

from swirengine import Rectangle2D, Scene, TileMap2D
from swirengine.graphics.batching import SpriteBatch, SpriteBatchKey
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.primitives import Sprite2D
from swirengine.graphics.renderer2d_power import Renderer2DPowerPass


class _Host:
    width = 320
    height = 180

    def __init__(self) -> None:
        self.stats = SimpleNamespace(
            objects_culled_2d=0,
            tilemap_cells_considered=0,
            tilemap_cells_visible=0,
        )

    @staticmethod
    def _center(obj, camera):
        if obj.screen_space:
            return float(obj.x), float(obj.y)
        return float(obj.x) - camera.x, float(obj.y) - camera.y


def test_tilemap_children_remain_registered_but_scene_updates_only_the_root():
    scene = Scene()
    tilemap = TileMap2D("tiles.png", 8, 8, 16, 16, 4, 4).fill(1)
    scene.add(tilemap)
    scene.add_many(*tilemap.children)

    assert len(scene.objects) == 65
    assert scene.render_objects == (tilemap,)

    scene.diagnostics.reset()
    tilemap.diagnostics.reset()
    scene.update(1 / 60)

    assert scene.diagnostics.object_updates == 1
    assert tilemap.diagnostics.transform_sprite_visits == 0
    assert scene.render_objects is scene.render_objects
    assert scene.diagnostics.render_snapshot_rebuilds == 0


def test_unchanged_tilemap_skips_full_pool_transform_walk():
    tilemap = TileMap2D("tiles.png", 32, 32, 16, 16, 4, 4).fill(1)
    tilemap.diagnostics.reset()

    for _ in range(120):
        tilemap.update(1 / 60)

    assert tilemap.diagnostics.transform_syncs == 0
    assert tilemap.diagnostics.transform_sprite_visits == 0

    tilemap.x = 10
    tilemap.update(1 / 60)
    assert tilemap.diagnostics.transform_syncs == 1
    assert tilemap.diagnostics.transform_sprite_visits == 32 * 32

    tilemap.update(1 / 60)
    assert tilemap.diagnostics.transform_syncs == 1


def test_tilemap_viewport_query_is_bounded_by_local_cells_not_world_size():
    tilemap = TileMap2D("tiles.png", 128, 128, 16, 16, 4, 4).fill(1)

    visible = tuple(
        tilemap.iter_visible_sprites(
            160,
            90,
            320,
            180,
            zoom=1.0,
        )
    )

    assert tilemap.tile_count == 128 * 128
    assert tilemap.diagnostics.last_visibility_candidates <= 240
    assert len(visible) == tilemap.diagnostics.last_visible_sprites
    assert len(visible) <= tilemap.diagnostics.last_visibility_candidates


def test_power_pass_culls_far_explicit_size_objects_conservatively():
    power = Renderer2DPowerPass()
    host = _Host()
    camera = Camera2D()
    near = Rectangle2D(0, 0, 20, 20)
    far = Rectangle2D(50_000, 50_000, 20, 20)
    hud = Rectangle2D(50_000, 50_000, 20, 20, screen_space=True)

    visible = tuple(power.iter_renderables(host, (near, far, hud), camera))

    assert visible == (near, hud)
    assert host.stats.objects_culled_2d == 1


def test_sprite_cpu_staging_is_reused_until_capacity_must_grow():
    power = Renderer2DPowerPass(initial_sprite_capacity=4)
    host = _Host()
    camera = Camera2D()
    sprites = tuple(Sprite2D("tiles.png", x=float(index), width=16, height=16) for index in range(4))
    batch = SpriteBatch(SpriteBatchKey("tiles.png", 0, False), sprites)

    first_identity = power.staging_identity
    first = power._sprite_vertices(host, batch, 16, 16, camera)
    second = power._sprite_vertices(host, batch, 16, 16, camera)

    assert first.shape == (24, 8)
    assert second.shape == (24, 8)
    assert power.staging_identity == first_identity
    assert power.staging_reallocations == 0

    bigger = SpriteBatch(
        SpriteBatchKey("tiles.png", 0, False),
        sprites + (Sprite2D("tiles.png", width=16, height=16),),
    )
    power._sprite_vertices(host, bigger, 16, 16, camera)
    grown_identity = power.staging_identity
    assert grown_identity != first_identity
    assert power.sprite_capacity == 8
    assert power.staging_reallocations == 1

    power._sprite_vertices(host, bigger, 16, 16, camera)
    assert power.staging_identity == grown_identity
    assert power.staging_reallocations == 1
