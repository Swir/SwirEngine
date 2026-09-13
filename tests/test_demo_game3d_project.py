from __future__ import annotations

import importlib
import sys
from pathlib import Path

import swirengine as sw

PROJECT_ROOT = Path(__file__).resolve().parents[1] / "demo_projects" / "neon_cube_hunt_3d"


def load_demo_module():
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        return importlib.import_module("neon_cube_hunt.game")
    finally:
        sys.path.remove(str(PROJECT_ROOT))


def no_keys(_name: str) -> bool:
    return False


def test_official_demo_builds_complete_3d_game_from_public_api() -> None:
    module = load_demo_module()
    game, demo = module.create_demo_game()

    assert game.mode == "3d"
    assert game.shadows_enabled is True
    assert game.shadow_settings.resolution == 1024
    assert game.postprocess.enabled is True
    assert game.postprocess.fxaa is True
    assert game.scene.require("player") is demo.player
    assert len(game.scene.tagged("collectible")) == 6
    assert len(game.scene.tagged("hazard")) == 3
    assert len(game.scene.tagged("wall")) == 4
    assert len(game.scene.tagged("progress")) == 6
    assert len(game.scene.objects) >= 23
    assert demo.player.material is not None
    assert demo.player.material.pbr_enabled is True


def test_demo_movement_collection_damage_and_reset_are_deterministic() -> None:
    module = load_demo_module()
    _game, demo = module.create_demo_game()

    start = sw.Vec3(demo.player.position.x, demo.player.position.y, demo.player.position.z)
    demo.step(0.1, lambda name: name in {"w", "d"})
    assert demo.player.position.x > start.x
    assert demo.player.position.z < start.z

    collectible = demo.collectibles[0]
    demo.player.position = sw.Vec3(
        collectible.position.x,
        collectible.position.y,
        collectible.position.z,
    )
    demo.step(0.0, no_keys)
    assert demo.score == 1
    assert collectible.visible is False
    assert demo.progress_markers[0].visible is True

    hazard = demo.hazards[0]
    demo.player.position = sw.Vec3(hazard.position.x, hazard.position.y, hazard.position.z)
    demo.damage_cooldown = 0.0
    demo.step(0.0, no_keys)
    assert demo.lives == 2
    assert demo.player.position == sw.Vec3()

    demo.reset_round()
    assert demo.score == 0
    assert demo.lives == 3
    assert all(item.visible for item in demo.collectibles)
    assert not any(item.visible for item in demo.progress_markers)


def test_demo_smoke_frame_limit_stops_real_game_loop_contract() -> None:
    module = load_demo_module()
    game, demo = module.create_demo_game(smoke_frames=2)

    game.running = True
    demo.step(0.0, no_keys)
    assert game.running is True
    demo.step(0.0, no_keys)
    assert game.running is False
    assert demo.frame_count == 2
