from __future__ import annotations

import os
import time
from dataclasses import dataclass

import numpy as np

from swirengine import Color, Cube3D, Game, Scene, Vec3
from swirengine.character import CharacterConfig3D, CharacterController3D, CharacterInput3D
from swirengine.editor_authoring_workspace import EditorAuthoringWorkspace
from swirengine.gpu_particles import GPUParticleBlendMode, GPUParticleEmitter3D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.lights import DirectionalLight3D
from swirengine.graphics.renderer2 import Decal3D, Renderer2Planner, Renderer2Settings
from swirengine.multiplayer14 import (
    LagCompensationHistory,
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
from swirengine.terrain import HeightmapTerrain, TerrainConfig

SMOKE_FRAMES = int(os.environ.get("SWIR_1_4_SMOKE_FRAMES", "0"))
FIXED_DT = 1.0 / 60.0


@dataclass(frozen=True, slots=True)
class ShowcaseDiagnostics:
    terrain_chunks: int
    terrain_triangles: int
    streamed_chunks: int
    physics_bodies: int
    character_sweeps: int
    renderer_passes: int
    renderer_draw_calls: int
    particle_emitted: int
    editor_targets: int
    network_delta_entities: int
    network_bytes: int


def _heightmap(size: int = 65) -> np.ndarray:
    z, x = np.mgrid[0:size, 0:size]
    return (
        np.sin(x * 0.17) * 1.4
        + np.cos(z * 0.11) * 1.1
        + np.sin((x + z) * 0.045) * 2.2
    ).astype("f4")


def _terrain() -> HeightmapTerrain:
    return HeightmapTerrain(
        _heightmap(),
        config=TerrainConfig(
            cell_size=1.5,
            height_scale=0.75,
            chunk_cells=16,
            lod_steps=(1, 2, 4),
            lod_distances=(42.0, 84.0),
            mesh_cache_size=48,
        ),
        origin=Vec3(-48.0, -2.0, -60.0),
    )


def _body(
    target: Cube3D,
    *,
    width: float,
    height: float,
    depth: float,
    body_type: str,
) -> PhysicsBody3D:
    collider = BoxCollider3D(target, width=width, height=height, depth=depth)
    return PhysicsBody3D(target, collider, body_type=body_type)  # type: ignore[arg-type]


def _registry() -> ReplicationRegistry:
    registry = ReplicationRegistry()
    registry.define(
        "transform",
        (
            ReplicationField("x"),
            ReplicationField("y"),
            ReplicationField("z"),
        ),
    )
    registry.define("state", ("hp", "mode"))
    return registry


def _snapshot(
    registry: ReplicationRegistry,
    *,
    tick: int,
    server_time: float,
    position: Vec3,
    hp: int = 100,
) -> WorldSnapshot:
    entity = registry.capture(
        1,
        {
            "transform": {
                "x": float(position.x),
                "y": float(position.y),
                "z": float(position.z),
            },
            "state": {"hp": int(hp), "mode": "run"},
        },
    )
    return WorldSnapshot(tick, server_time, (entity,))


def run_headless_probe() -> ShowcaseDiagnostics:
    """Exercise the complete 1.4 integration surface without creating an OpenGL context."""
    terrain = _terrain()
    scene = Scene()
    streamer = terrain.large_world_provider(lod=1)
    from swirengine.large_world import LargeWorldStreamer

    world_streamer = LargeWorldStreamer(
        scene,
        streamer,
        settings=terrain.large_world_settings(
            active_radius_chunks=1,
            preload_radius_chunks=1,
            retention_radius_chunks=2,
            max_activations_per_update=9,
        ),
    )
    stream_result = world_streamer.update((0.0, -18.0))
    selections = terrain.select_chunks(0.0, -18.0, radius_chunks=1)
    terrain_triangles = sum(terrain.chunk_mesh(item.key, item.lod).triangle_count for item in selections)

    floor = scene.add(Cube3D(position=Vec3(0.0, -1.25, 0.0), scale=Vec3(18.0, 0.5, 12.0)))
    player = scene.add(Cube3D(position=Vec3(0.0, 0.9, 0.0), size=0.8, name="showcase-player"))
    crate = scene.add(Cube3D(position=Vec3(2.0, 3.0, -2.0), size=0.9, name="showcase-crate"))
    scene.add(DirectionalLight3D(direction=Vec3(-0.6, -1.0, -0.35), intensity=1.8))
    scene.add(
        Decal3D(
            position=Vec3(0.0, -0.95, -2.0),
            size=Vec3(4.0, 0.25, 4.0),
            color=Color(0.05, 0.75, 1.0, 0.55),
        )
    )

    physics = PhysicsScene3D(fixed_dt=1.0 / 120.0, solver_iterations=6)
    physics.add(_body(floor, width=18.0, height=0.5, depth=12.0, body_type="static"))
    physics.add(_body(crate, width=0.9, height=0.9, depth=0.9, body_type="dynamic"))
    controller = CharacterController3D(
        player,
        physics,
        config=CharacterConfig3D(walk_speed=4.0, ground_acceleration=80.0, step_height=0.35),
    )
    for frame in range(24):
        controller.update(CharacterInput3D(move_x=0.75, jump=frame == 12), FIXED_DT)
        physics.step(FIXED_DT)

    emitter = scene.add(
        GPUParticleEmitter3D(
            position=Vec3(0.0, 1.2, -2.0),
            capacity=4096,
            rate=900.0,
            blend_mode=GPUParticleBlendMode.ADDITIVE,
            seed=1405,
        )
    )
    emitter.burst(512)
    emitter.update(FIXED_DT)

    camera = Camera3D(position=Vec3(10.0, 8.0, 14.0), target=Vec3(0.0, 0.0, -5.0))
    plan = Renderer2Planner(
        Renderer2Settings(
            shadow_cascades=4,
            ssao=True,
            bloom=True,
            decals=True,
            hdr=True,
        )
    ).plan(scene, camera, width=960, height=540)

    editor = EditorAuthoringWorkspace(scene, project_name="Neon Frontier 1.4")
    editor.select(player)
    editor.select(crate, mode="add")
    editor.configure_viewport(snap_enabled=True, translation_snap=0.25)
    authoring = editor.apply_selected_gizmo("translate", "z", -0.26)
    assert authoring.transaction.edit_count == 2
    editor.undo()
    editor.redo()

    registry = _registry()
    first = _snapshot(registry, tick=100, server_time=5.0, position=Vec3(0.0, 0.9, 0.0))
    second = _snapshot(registry, tick=101, server_time=5.05, position=player.position, hp=97)
    delta = SnapshotDelta.between(first, second)
    assert delta.apply(first) == second
    snapshots = SnapshotBuffer(registry=registry)
    snapshots.push(first)
    snapshots.push(second)
    interpolated = snapshots.sample(5.025)
    assert interpolated.entities
    history = LagCompensationHistory(registry=registry)
    history.record(first)
    history.record(second)
    assert history.rewind(5.025).entities
    packet = MultiplayerPacketCodec.delta_packet(delta)
    bandwidth = MultiplayerBandwidthDiagnostics()
    encoded = packet.to_bytes()
    bandwidth.record_sent(encoded, channel="delta")

    diagnostics = ShowcaseDiagnostics(
        terrain_chunks=len(selections),
        terrain_triangles=terrain_triangles,
        streamed_chunks=stream_result.diagnostics.active_chunks,
        physics_bodies=physics.diagnostics.body_count,
        character_sweeps=controller.diagnostics.sweeps,
        renderer_passes=plan.diagnostics.frame_passes,
        renderer_draw_calls=plan.diagnostics.estimated_draw_calls,
        particle_emitted=emitter.diagnostics.emitted_total,
        editor_targets=editor.selection.count,
        network_delta_entities=len(delta.entities),
        network_bytes=len(encoded),
    )
    if diagnostics.terrain_chunks < 1 or diagnostics.streamed_chunks < 1:
        raise AssertionError("terrain/streaming integration did not activate")
    if diagnostics.physics_bodies < 2 or diagnostics.character_sweeps < 1:
        raise AssertionError("physics/controller integration did not execute")
    if diagnostics.renderer_passes < 4 or diagnostics.renderer_draw_calls < 1:
        raise AssertionError("Renderer 2.0 planning did not produce the expected workload")
    if diagnostics.particle_emitted < 512 or diagnostics.editor_targets != 2:
        raise AssertionError("VFX/editor integration did not execute")
    if diagnostics.network_delta_entities != 1 or diagnostics.network_bytes <= 0:
        raise AssertionError("Multiplayer 2.0 integration did not produce a network delta")
    return diagnostics


def runtime_probe() -> int:
    """Verify the packaged native renderer and the headless 1.4 integration surface."""
    import glcontext
    import glfw
    import moderngl

    version = glfw.get_version_string()
    if isinstance(version, bytes):
        version = version.decode("utf-8", errors="replace")
    diagnostics = run_headless_probe()
    print(f"GLFW runtime OK: {version}")
    print(f"ModernGL runtime OK: {moderngl.__version__}")
    print(f"glcontext runtime OK: {glcontext.__file__}")
    print(f"SwirEngine 1.4 integration probe OK: {diagnostics}")
    return 0


class NeonFrontier14:
    """Production-scale, asset-free integration demo for the SwirEngine 1.4 release gate."""

    def __init__(self) -> None:
        self.game = Game("Neon Frontier 1.4", 960, 540, mode="3d", vsync=False, target_fps=240)
        self.game.camera.position = Vec3(12.0, 9.0, 16.0)
        self.game.camera.look_at(Vec3(0.0, 0.0, -7.0))
        self.game.configure_renderer2(
            True,
            shadow_cascades=4,
            shadow_resolution=1024,
            shadow_distance=110.0,
            ssao=True,
            ssao_samples=16,
            bloom=True,
            bloom_levels=4,
            decals=True,
            max_decals=64,
            hdr=True,
        )
        self.game.configure_postprocess(enabled=True, tone_mapping="aces", exposure=1.05, fxaa=True)
        self.frames = 0
        self.elapsed = 0.0
        self.network_updates = 0
        self.last_snapshot: WorldSnapshot | None = None
        self.registry = _registry()
        self.snapshots = SnapshotBuffer(registry=self.registry)
        self.bandwidth = MultiplayerBandwidthDiagnostics()

        self.terrain = _terrain()
        from swirengine.large_world import LargeWorldStreamer

        self.streamer = LargeWorldStreamer(
            self.game.scene,
            self.terrain.large_world_provider(lod=1),
            settings=self.terrain.large_world_settings(
                active_radius_chunks=1,
                preload_radius_chunks=1,
                retention_radius_chunks=2,
                max_activations_per_update=9,
                max_deactivations_per_update=9,
            ),
        )
        self.streamer.update((0.0, -18.0))

        self.floor = self.game.add(
            Cube3D(
                position=Vec3(0.0, -1.25, 0.0),
                scale=Vec3(18.0, 0.5, 12.0),
                color=Color(0.06, 0.08, 0.12, 1.0),
                name="physics-floor",
            )
        )
        self.player = self.game.add(
            Cube3D(
                position=Vec3(0.0, 0.9, 0.0),
                size=0.8,
                color=Color(0.1, 0.85, 1.0, 1.0),
                name="network-player",
            )
        )
        self.crate = self.game.add(
            Cube3D(
                position=Vec3(2.0, 3.0, -2.0),
                size=0.9,
                color=Color(1.0, 0.38, 0.1, 1.0),
                name="physics-crate",
            )
        )
        self.game.directional_light(direction=Vec3(-0.6, -1.0, -0.35), intensity=1.9)
        self.game.decal(
            position=Vec3(0.0, -0.95, -2.0),
            size=Vec3(4.0, 0.25, 4.0),
            color=Color(0.05, 0.75, 1.0, 0.55),
            opacity=0.8,
        )
        self.effects = self.game.gpu_particles(
            position=Vec3(0.0, 1.2, -2.0),
            capacity=8192,
            rate=1200.0,
            lifetime=(0.7, 1.7),
            velocity_min=Vec3(-1.4, 0.8, -1.4),
            velocity_max=Vec3(1.4, 4.8, 1.4),
            gravity=Vec3(0.0, -3.5, 0.0),
            blend_mode=GPUParticleBlendMode.ADDITIVE,
            seed=1405,
        )
        self.effects.burst(1024)

        self.physics = PhysicsScene3D(fixed_dt=1.0 / 120.0, solver_iterations=6)
        self.physics.add(_body(self.floor, width=18.0, height=0.5, depth=12.0, body_type="static"))
        self.physics.add(_body(self.crate, width=0.9, height=0.9, depth=0.9, body_type="dynamic"))
        self.controller = CharacterController3D(
            self.player,
            self.physics,
            config=CharacterConfig3D(walk_speed=4.0, ground_acceleration=80.0, step_height=0.35),
        )

        self.editor = EditorAuthoringWorkspace(self.game.scene, project_name="Neon Frontier 1.4")
        self.editor.select(self.player)
        self.editor.select(self.crate, mode="add")
        self.editor.configure_viewport(snap_enabled=True, translation_snap=0.25)
        edit = self.editor.apply_selected_gizmo("translate", "z", -0.26)
        if edit.transaction.edit_count != 2:
            raise RuntimeError("1.4 showcase editor transaction failed")

        self.game.update(self._update)

    def _replicate(self) -> None:
        snapshot = _snapshot(
            self.registry,
            tick=self.frames,
            server_time=self.elapsed,
            position=self.player.position,
            hp=max(1, 100 - self.frames // 30),
        )
        self.snapshots.push(snapshot)
        if self.last_snapshot is not None:
            delta = SnapshotDelta.between(self.last_snapshot, snapshot)
            packet = MultiplayerPacketCodec.delta_packet(delta)
            self.bandwidth.record_sent(packet.to_bytes(), channel="delta")
            self.network_updates += 1
        self.last_snapshot = snapshot

    def _update(self, dt: float) -> None:
        self.frames += 1
        self.elapsed += dt
        command = CharacterInput3D(
            move_x=0.65,
            move_z=0.18,
            jump=self.frames == 45,
            sprint=self.frames % 120 > 80,
        )
        self.controller.update(command, dt)
        self.physics.step(dt)
        self.effects.update(dt)
        self.streamer.update((self.player.position.x, self.player.position.z - 18.0))
        if self.frames == 1 or self.frames % 6 == 0:
            self._replicate()
        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES:
            if self.frames < SMOKE_FRAMES:
                raise AssertionError("1.4 smoke stopped before the requested frame count")
            if self.streamer.diagnostics.active_chunks < 1:
                raise AssertionError("terrain streaming did not activate during the real render smoke")
            if self.controller.diagnostics.sweeps < 1:
                raise AssertionError("character controller did not execute during the real render smoke")
            if self.effects.diagnostics.emitted_total < 1024:
                raise AssertionError("GPU VFX scheduler did not emit during the real render smoke")
            if self.network_updates < 1:
                raise AssertionError("Multiplayer 2.0 did not produce deltas during the real render smoke")
            print(
                "Neon Frontier 1.4 smoke OK: "
                f"frames={self.frames}, active_chunks={self.streamer.diagnostics.active_chunks}, "
                f"physics_bodies={self.physics.diagnostics.body_count}, "
                f"character_sweeps={self.controller.diagnostics.sweeps}, "
                f"particles={self.effects.diagnostics.emitted_total}, "
                f"editor_targets={self.editor.selection.count}, network_updates={self.network_updates}"
            )


def main() -> int:
    if os.environ.get("SWIR_DEMO_RUNTIME_PROBE") == "1":
        return runtime_probe()
    if os.environ.get("SWIR_1_4_HEADLESS_PROBE") == "1":
        started = time.perf_counter()
        diagnostics = run_headless_probe()
        elapsed = time.perf_counter() - started
        print(f"Neon Frontier 1.4 headless integration OK in {elapsed:.4f}s: {diagnostics}")
        return 0
    NeonFrontier14().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
