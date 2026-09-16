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
from swirengine.large_world import LargeWorldStreamer
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


def _stream_focus(terrain: HeightmapTerrain, x: float, z: float) -> tuple[float, float]:
    """Map terrain world coordinates onto LargeWorld's zero-based chunk address plane."""
    return float(x) - terrain.origin.x, float(z) - terrain.origin.z


def _make_streamer(scene: Scene, terrain: HeightmapTerrain) -> LargeWorldStreamer:
    return LargeWorldStreamer(
        scene,
        terrain.large_world_provider(lod=1),
        settings=terrain.large_world_settings(
            active_radius_chunks=1,
            preload_radius_chunks=1,
            retention_radius_chunks=2,
            max_activations_per_update=9,
        ),
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
        (ReplicationField("x"), ReplicationField("y"), ReplicationField("z")),
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


def _configure_physics(
    scene: Scene,
) -> tuple[PhysicsScene3D, Cube3D, Cube3D, Cube3D, CharacterController3D]:
    floor = scene.add(
        Cube3D(
            position=Vec3(0.0, -1.25, 0.0),
            scale=Vec3(18.0, 0.5, 12.0),
            color=Color(0.06, 0.08, 0.12, 1.0),
            name="physics-floor",
        )
    )
    player = scene.add(
        Cube3D(
            position=Vec3(0.0, 0.9, 0.0),
            size=0.8,
            color=Color(0.1, 0.85, 1.0, 1.0),
            name="network-player",
        )
    )
    crate = scene.add(
        Cube3D(
            position=Vec3(2.0, 3.0, -2.0),
            size=0.9,
            color=Color(1.0, 0.38, 0.1, 1.0),
            name="physics-crate",
        )
    )
    physics = PhysicsScene3D(fixed_dt=1.0 / 120.0, solver_iterations=6)
    physics.add(_body(floor, width=18.0, height=0.5, depth=12.0, body_type="static"))
    physics.add(_body(crate, width=0.9, height=0.9, depth=0.9, body_type="dynamic"))
    controller = CharacterController3D(
        player,
        physics,
        config=CharacterConfig3D(
            walk_speed=4.0,
            ground_acceleration=80.0,
            step_height=0.35,
        ),
    )
    return physics, floor, player, crate, controller


def run_headless_probe() -> ShowcaseDiagnostics:
    """Exercise the complete 1.4 integration surface without creating an OpenGL context."""
    terrain = _terrain()
    scene = Scene()
    streamer = _make_streamer(scene, terrain)
    stream_result = streamer.update(_stream_focus(terrain, 0.0, 0.0))
    selections = terrain.select_chunks(0.0, 0.0, radius_chunks=1)
    terrain_triangles = sum(
        terrain.chunk_mesh(item.key, item.lod).triangle_count for item in selections
    )

    physics, _floor, player, crate, controller = _configure_physics(scene)
    scene.add(DirectionalLight3D(direction=Vec3(-0.6, -1.0, -0.35), intensity=1.8))
    scene.add(
        Decal3D(
            position=Vec3(0.0, -0.95, -2.0),
            size=Vec3(4.0, 0.25, 4.0),
            color=Color(0.05, 0.75, 1.0, 0.55),
        )
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
    assert snapshots.sample(5.025).entities
    history = LagCompensationHistory(registry=registry)
    history.record(first)
    history.record(second)
    assert history.rewind(5.025).entities
    encoded = MultiplayerPacketCodec.delta_packet(delta).to_bytes()
    bandwidth = MultiplayerBandwidthDiagnostics()
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
        network_delta_entities=len(delta.upserts),
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
    """Verify packaged native renderer imports plus the complete headless integration path."""
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
        self.game.configure_postprocess(
            enabled=True,
            tone_mapping="aces",
            exposure=1.05,
            fxaa=True,
        )
        self.frames = 0
        self.elapsed = 0.0
        self.network_updates = 0
        self.last_snapshot: WorldSnapshot | None = None
        self.registry = _registry()
        self.snapshots = SnapshotBuffer(registry=self.registry)
        self.bandwidth = MultiplayerBandwidthDiagnostics()

        self.terrain = _terrain()
        self.streamer = _make_streamer(self.game.scene, self.terrain)
        self.streamer.update(_stream_focus(self.terrain, 0.0, 0.0))

        self.physics, self.floor, self.player, self.crate, self.controller = _configure_physics(
            self.game.scene
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

        self.editor = EditorAuthoringWorkspace(
            self.game.scene,
            project_name="Neon Frontier 1.4",
        )
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
            self.bandwidth.record_sent(
                MultiplayerPacketCodec.delta_packet(delta).to_bytes(),
                channel="delta",
            )
            self.network_updates += 1
        self.last_snapshot = snapshot

    def _update(self, dt: float) -> None:
        self.frames += 1
        self.elapsed += dt
        self.controller.update(
            CharacterInput3D(
                move_x=0.65,
                move_z=0.18,
                jump=self.frames == 45,
                sprint=self.frames % 120 > 80,
            ),
            dt,
        )
        self.physics.step(dt)
        self.effects.update(dt)
        self.streamer.update(
            _stream_focus(self.terrain, self.player.position.x, self.player.position.z)
        )
        if self.frames == 1 or self.frames % 6 == 0:
            self._replicate()
        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if not SMOKE_FRAMES:
            return
        if self.frames < SMOKE_FRAMES:
            raise AssertionError("1.4 smoke stopped before the requested frame count")
        if self.streamer.diagnostics.active_chunks < 1:
            raise AssertionError("terrain streaming did not activate during real rendering")
        if self.controller.diagnostics.sweeps < 1:
            raise AssertionError("character controller did not execute during real rendering")
        if self.effects.diagnostics.emitted_total < 1024:
            raise AssertionError("GPU VFX scheduler did not emit during real rendering")
        if self.network_updates < 1:
            raise AssertionError("Multiplayer 2.0 did not produce deltas during real rendering")
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
