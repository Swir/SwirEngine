import pytest

from swirengine import TileMap2D


def make_map() -> TileMap2D:
    return TileMap2D("tiles.png", 3, 2, 16, 16, 4, 2)


def test_tilemap_allocates_fixed_sprite_pool():
    tilemap = make_map()
    assert len(tilemap.children) == 6
    assert tilemap.tile_count == 0
    assert all(not sprite.visible for sprite in tilemap.children)


def test_set_tile_updates_uv_and_visibility():
    tilemap = make_map()
    tilemap.set_tile(1, 0, 5)
    sprite = tilemap.children[1]
    assert tilemap.get_tile(1, 0) == 5
    assert sprite.visible
    assert sprite.uv_rect == (0.25, 0.0, 0.5, 0.5)


def test_tilemap_fill_clear_and_rows():
    tilemap = make_map().fill(1)
    assert tilemap.tile_count == 6
    tilemap.clear()
    assert tilemap.tile_count == 0
    tilemap.load_rows([[0, 1, None], [2, None, 3]])
    assert tilemap.tile_count == 4
    assert tilemap.get_tile(2, 1) == 3


def test_tilemap_coordinate_helpers_and_transform_sync():
    tilemap = make_map()
    tilemap.x = 100
    tilemap.y = 50
    tilemap.layer = 7
    tilemap.set_tile(0, 0, 0)
    tilemap.update(0.016)
    assert tilemap.cell_to_world(0, 0) == (108.0, 58.0)
    assert tilemap.world_to_cell(132, 75) == (2, 1)
    assert tilemap.children[0].layer == 7
    assert (tilemap.children[0].x, tilemap.children[0].y) == (108.0, 58.0)


def test_tilemap_rejects_bad_cells_tiles_and_shapes():
    tilemap = make_map()
    with pytest.raises(IndexError):
        tilemap.set_tile(3, 0, 0)
    with pytest.raises(IndexError):
        tilemap.set_tile(0, 0, 8)
    with pytest.raises(ValueError):
        tilemap.load_rows([[0, 1]])
