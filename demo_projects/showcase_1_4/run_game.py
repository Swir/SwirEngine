from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from swirengine import Color, Cube3D, Game, Vec3
from swirengine.character import CharacterConfig3D, CharacterController3D, CharacterInput3D
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession
from swirengine.large_world import LargeWorldStreamer
from swirengine.multiplayer14 import (
    MultiplayerBandwidthDiagnostics,
    MultiplayerPacketCodec,
    ReplicationField,
    ReplicationRegistry,
    SnapshotBuffer,
    SnapshotDelta,
    WorldSnapshot,
)
from swirengine.physics import BoxCollider3D
from swirengine.physics.dynamics3d import PhysicsBody3D, PhysicsScene3D
from swirengine.terrain import HeightmapTerrain, TerrainCollider3D, TerrainConfig


@dataclass
class PhysicsTarget:
    position: Vec3 = field(default_factory=Vec3)


@dataclass(frozen=True, slots=True)
class ShowcaseReport:
    terrain_chunks: int
    streamed_objects: int
    controller_x: float
    editor_selection: int
    editor_cube_x: float
    particle_capacity: int
    particle_queued: int
    snapshot_bytes: int
    delta_bytes: int
    interpolated_x: float


def _static_box(
    scene: PhysicsScene3D,
    position: Vec3,
    *,
    width: float,
    height: float,
    depth: float,
) -> None:
    target = PhysicsTarget(position)
    collider = BoxCollider3D(target, width=width, height=height, depth=depth)
    scene.add(PhysicsBody3D(target, collider, body_type="static"))


def _build_terrain() -> HeightmapTerrain:
    size = 65
    z, x = np.mgrid[0:size, 0:size]
    heightmap = (
        np.sin(x * 0.12) * 2.25
        + np.cos(z * 0.09) * 1.75
        + np.sin((x + z) * 0.04) * 2.5
    ).astype("f4")
    return HeightmapTerrain(
        heightmap,
        config=TerrainConfig(
            cell_size=2.0,
            height_scale=1.0,
            chunk_cells=8,
            lod_steps=(1, 2, 4),
            lod_distances=(45.0, 90.0),
        ),
    )


def _exercise_character() -> tuple[PhysicsTarget, CharacterController3D]:
    physics = PhysicsScene3D(gravity=Vec3())
    _static_box(
        physics,
        Vec3(0.0, -0.5, 0.0),
        width=32.0,
        height=1.0,
        depth=10.0,
    )
    _static_box(
        physics,
        Vec3(3.0, 0.15, 0.0),
        width=0.8,
        height=0.3,
        depth=3.0,
    )
    target = PhysicsTarget(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(
        target,
        physics,
        config=CharacterConfig3D(
            walk_speed=5.0,
            ground_acceleration=120.0,
            step_height=0.4,
        ),
    )
    for frame in range(180):
        controller.update(CharacterInput3D(move_x=1.0, jump=frame == 120), 1.0 / 60.0)
    if target.position.x <= 1.0:
        raise RuntimeError("showcase controller failed to traverse the validation course")
    return target, controller


def _network_snapshot(registry: ReplicationRegistry, tick: int, x: float) -> WorldSnapshot:
    player = registry.capture(
        1,
        {
            "transform": {"x": x, "y": 0.0, "state": "run"},
            "health": {"hp": 100 - (tick - 100)},
        },
    )
    return WorldSnapshot(tick, tick / 20.0, (player,))


def run_showcase(*, render: bool = False, render_frames: int = 12) -> ShowcaseReport:
    game = Game("SwirEngine 1.4 Production Showcase", 1280, 720, mode="3d", vsync=False)
    game.configure_renderer2(
        True,
        shadow_cascades=3,
        shadow_resolution=1024,
        shadow_distance=100.0,
        ssao=True,
        bloom=True,
        decals=True,
        hdr=True,
    )
    game.configure_postprocess(enabled=True, tone_mapping="aces", exposure=1.0, fxaa=True)
    game.directional_light(
        direction=Vec3(-0.55, -1.0, -0.35),
        intensity=1.6,
        color=Color(1.0, 0.94, 0.86, 1.0),
    )

    terrain = _build_terrain()
    focus_x = terrain.world_width * 0.5
    focus_z = terrain.world_depth * 0.5
    selections = terrain.select_chunks(focus_x, focus_z, radius_chunks=2)
    if not selections:
        raise RuntimeError("showcase terrain produced no visible chunks")
    ground = TerrainCollider3D(terrain).raycast_down(focus_x, 100.0, focus_z, 250.0)
    if ground is None:
        raise RuntimeError("showcase terrain collision ray missed")

    streamer = LargeWorldStreamer(
        game.scene,
        terrain.large_world_provider(lod=1),
        settings=terrain.large_world_settings(
            active_radius_chunks=1,
            preload_radius_chunks=1,
            retention_radius_chunks=2,
            max_activations_per_update=9,
        ),
    )
    stream_result = streamer.update((focus_x, focus_z))
    if stream_result.diagnostics.active_chunks <= 0:
        raise RuntimeError("showcase world streamer failed to activate terrain chunks")

    editor_cube = game.add(
        Cube3D(
            position=Vec3(0.0, ground.point.y + 1.0, -5.0),
            scale=Vec3(1.5, 1.5, 1.5),
            color=Color(0.12, 0.62, 1.0, 1.0),
        )
    )
    authoring = EditorAuthoringSession(SceneInspector(game.scene))
    authoring.select(editor_cube)
    authoring.apply_gizmo("translate", "x", 1.25)
    if abs(editor_cube.position.x - 1.25) > 1e-6:
        raise RuntimeError("showcase editor authoring transform did not apply")

    character, controller = _exercise_character()
    if controller.diagnostics.sweeps <= 0:
        raise RuntimeError("showcase character controller did not execute collision sweeps")

    particles = game.gpu_particles(
        position=Vec3(editor_cube.position.x, editor_cube.position.y + 1.0, editor_cube.position.z),
        capacity=4096,
        rate=900.0,
        lifetime=(0.7, 1.6),
        gravity=Vec3(0.0, -3.5, 0.0),
        start_color=Color(0.2, 0.8, 1.0, 1.0),
        end_color=Color(0.1, 0.2, 1.0, 0.0),
        emissive_strength=2.5,
        trail_enabled=True,
    )
    particles.burst(256)
    particles.update(1.0 / 60.0)
    particle_diagnostics = particles.diagnostics
    if particle_diagnostics.queued <= 0:
        raise RuntimeError("showcase GPU VFX scheduler did not queue particles")

    registry = ReplicationRegistry()
    registry.define(
        "transform",
        (
            ReplicationField("x"),
            ReplicationField("y"),
            ReplicationField("state", interpolate=False),
        ),
    )
    registry.define("health", ("hp",))
    first = _network_snapshot(registry, 100, character.position.x - 0.5)
    second = _network_snapshot(registry, 101, character.position.x)
    delta = SnapshotDelta.between(first, second)
    if delta.apply(first) != second:
        raise RuntimeError("showcase multiplayer delta failed round-trip validation")

    buffer = SnapshotBuffer(registry=registry)
    buffer.push(first)
    buffer.push(second)
    sampled = buffer.sample((first.server_time + second.server_time) * 0.5)
    interpolated_x = float(sampled.entities[0].components["transform"]["x"])

    diagnostics = MultiplayerBandwidthDiagnostics()
    snapshot_packet = MultiplayerPacketCodec.snapshot_packet(second)
    delta_packet = MultiplayerPacketCodec.delta_packet(delta)
    snapshot_bytes = len(snapshot_packet.to_bytes())
    delta_bytes = len(delta_packet.to_bytes())
    diagnostics.record_sent(snapshot_packet.to_bytes(), channel="snapshot")
    diagnostics.record_sent(delta_packet.to_bytes(), channel="delta")
    if diagnostics.report(1.0).sent_bytes != snapshot_bytes + delta_bytes:
        raise RuntimeError("showcase multiplayer bandwidth accounting drifted")

    if render:
        remaining = max(1, int(render_frames))

        @game.update
        def stop_after_validation_frames(_dt: float) -> None:
            nonlocal remaining
            remaining -= 1
            if remaining <= 0:
                game.stop()

        game.run()

    return ShowcaseReport(
        terrain_chunks=len(selections),
        streamed_objects=len(game.scene.objects),
        controller_x=character.position.x,
        editor_selection=authoring.selection_snapshot.count,
        editor_cube_x=editor_cube.position.x,
        particle_capacity=particle_diagnostics.capacity,
        particle_queued=particle_diagnostics.queued,
        snapshot_bytes=snapshot_bytes,
        delta_bytes=delta_bytes,
        interpolated_x=interpolated_x,
    )


def main() -> None:
    render = os.environ.get("SWIR_1_4_SHOWCASE_RENDER") == "1"
    render_frames = int(os.environ.get("SWIR_1_4_SHOWCASE_FRAMES", "12"))
    report = run_showcase(render=render, render_frames=render_frames)
    print(
        "SwirEngine 1.4 showcase OK "
        f"terrain={report.terrain_chunks} "
        f"scene_objects={report.streamed_objects} "
        f"controller_x={report.controller_x:.3f} "
        f"editor_x={report.editor_cube_x:.3f} "
        f"particles={report.particle_queued}/{report.particle_capacity} "
        f"network={report.delta_bytes}/{report.snapshot_bytes}B "
        f"interpolated_x={report.interpolated_x:.3f}"
    )


if __name__ == "__main__":
    main()
