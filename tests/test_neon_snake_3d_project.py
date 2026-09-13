from __future__ import annotations

import importlib
import sys
from pathlib import Path

import swirengine as sw

PROJECT_ROOT = Path(__file__).resolve().parents[1] / "demo_projects" / "neon_snake_3d"


def load_demo_module():
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        return importlib.import_module("neon_snake.game")
    finally:
        sys.path.remove(str(PROJECT_ROOT))


def no_keys(_name: str) -> bool:
    return False


def test_snake_demo_builds_real_3d_scene_from_public_api() -> None:
    module = load_demo_module()
    game, demo = module.create_demo_game()

    assert game.mode == "3d"
    assert game.shadows_enabled is True
    assert game.shadow_settings.resolution == 1024
    assert game.postprocess.enabled is True
    assert game.postprocess.fxaa is True
    assert game.scene.require("snake-head") is demo.head
    assert game.scene.require("snake-food") is demo.food
    assert len(game.scene.tagged("wall")) == 4
    assert len(game.scene.tagged("body")) == module.INITIAL_LENGTH - 1
    assert demo.body_cells == [(0, 0), (-1, 0), (-2, 0), (-3, 0)]
    assert demo.food_cell == (4, 0)
    assert demo.score == 0


def test_snake_moves_eats_and_grows_deterministically() -> None:
    module = load_demo_module()
    _game, demo = module.create_demo_game()

    for _ in range(4):
        demo.step(module.MOVE_INTERVAL, no_keys)

    assert demo.body_cells[0] == (4, 0)
    assert demo.score == 1
    assert demo.high_score == 1
    assert len(demo.body_cells) == module.INITIAL_LENGTH + 1
    assert demo.food_cell == (4, -4)
    assert len([segment for segment in demo.segment_meshes if segment.visible]) == 4


def test_snake_rejects_immediate_reverse_direction() -> None:
    module = load_demo_module()
    _game, demo = module.create_demo_game()

    demo.step(module.MOVE_INTERVAL, lambda name: name == "a")

    assert demo.direction == (1, 0)
    assert demo.body_cells[0] == (1, 0)


def test_snake_wall_collision_resets_round_and_preserves_high_score() -> None:
    module = load_demo_module()
    _game, demo = module.create_demo_game()

    demo.high_score = 7
    for _ in range(module.GRID_HALF + 1):
        demo.step(module.MOVE_INTERVAL, no_keys)

    assert demo.deaths == 1
    assert demo.score == 0
    assert demo.high_score == 7
    assert demo.body_cells[0] == (0, 0)
    assert demo.direction == (1, 0)


def test_snake_turns_and_keeps_segments_on_grid() -> None:
    module = load_demo_module()
    _game, demo = module.create_demo_game()

    demo.step(module.MOVE_INTERVAL, lambda name: name == "w")
    demo.step(module.MOVE_INTERVAL, lambda name: name == "a")

    assert demo.body_cells[0] == (-1, -1)
    assert demo.direction == (-1, 0)
    assert len(set(demo.body_cells)) == len(demo.body_cells)
    assert demo.head.position == sw.Vec3(-module.CELL_SIZE, 0.02, -module.CELL_SIZE)


def test_snake_smoke_frame_limit_stops_real_game_loop_contract() -> None:
    module = load_demo_module()
    game, demo = module.create_demo_game(smoke_frames=2)

    game.running = True
    demo.step(0.0, no_keys)
    assert game.running is True
    demo.step(0.0, no_keys)
    assert game.running is False
    assert demo.frame_count == 2
