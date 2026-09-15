from __future__ import annotations

import os

from swirengine import (
    AABB3D,
    BoxCollider3D,
    CollisionWorld3D,
    Color,
    Cube3D,
    Game,
    InstancedCube3D,
    Material3D,
    ShaderMesh3D,
    Vec3,
    cube_mesh,
    shader_material_3d,
)
from swirengine.core.scene import Scene
from swirengine.gameplay import GameplayRuntime
from swirengine.large_world import (
    ChunkContent,
    ChunkDefinition,
    ChunkKey,
    LargeWorldSettings,
    LargeWorldStreamer,
)
from swirengine.navigation import NavigationAgent3D, NavigationGrid3D

SMOKE_FRAMES = int(os.environ.get("SWIR_1_3_SMOKE_FRAMES", "0"))


def runtime_probe() -> int:
    """Verify the packaged native renderer imports without opening a window."""
    import glcontext
    import glfw
    import moderngl

    version = glfw.get_version_string()
    if isinstance(version, bytes):
        version = version.decode("utf-8", errors="replace")
    print(f"GLFW runtime OK: {version}")
    print(f"ModernGL runtime OK: {moderngl.__version__}")
    print(f"glcontext runtime OK: {glcontext.__file__}")
    return 0


class NeonFrontier13:
    """Integrated asset-free game used as the SwirEngine 1.3 final validation project."""

    def __init__(self) -> None:
        self.game = Game("Neon Frontier 1.3", 960, 540, mode="3d", vsync=False, target_fps=240)
        self.game.camera.position = Vec3(10.0, 9.0, 14.0)
        self.game.camera.look_at(Vec3(0.0, 0.0, -5.0))
        self.frames = 0
        self.elapsed = 0.0
        self.pulses = 0
        self.collision_queries = 0

        self.gameplay = GameplayRuntime()
        self.gameplay.call_every(0.25, self._pulse)
        self._create_render_world()
        self._create_collision_world()
        self._create_navigation()
        self._create_streaming_world()
        self.game.update(self._update)

    def _create_render_world(self) -> None:
        material = Material3D(metallic=0.25, roughness=0.34)
        self.instances = InstancedCube3D(
            color=Color(0.12, 0.72, 1.0, 1.0),
            material=material,
            name="frontier-beacons",
        )
        for z in range(18):
            for x in range(18):
                self.instances.add_cube(
                    position=Vec3((x - 9) * 1.45, -1.8, -z * 1.45),
                    size=0.35 + ((x + z) % 4) * 0.06,
                    color=Color(0.12 + x * 0.012, 0.45 + z * 0.02, 1.0, 1.0),
                )
        self.game.add(self.instances)

        self.shader_material = shader_material_3d(
            hooks={
                "fragment_globals": "uniform float pulse;",
                "fragment_surface": (
                    "surface_rgba.rgb *= vec3(0.35 + 0.65 * pulse, 0.82, 1.0);"
                ),
            },
            uniforms={"pulse": 0.7},
        )
        self.core = ShaderMesh3D(
            cube_mesh(),
            self.shader_material,
            position=Vec3(0.0, 0.4, -5.0),
            scale=Vec3(1.2, 1.2, 1.2),
            color=Color(0.2, 0.9, 1.0, 1.0),
            name="frontier-core",
        )
        self.game.add(self.core)
        self.game.directional_light(direction=Vec3(-0.5, -1.0, -0.35), intensity=1.8)
        self.game.point_light(
            position=Vec3(0.0, 4.0, -5.0),
            color=Color(0.1, 0.65, 1.0, 1.0),
            intensity=8.0,
            range=24.0,
        )

    def _create_collision_world(self) -> None:
        self.collisions = CollisionWorld3D(cell_size=2.0)
        self.player = Cube3D(position=Vec3(0.2, 0.0, 0.2), size=0.6, name="validation-agent")
        self.player_collider = BoxCollider3D(self.player, tag="player")
        self.collisions.add(self.player_collider)
        self.obstacles: list[Cube3D] = []
        for index, (x, z) in enumerate(((3.0, 2.0), (5.0, 4.0), (7.0, 5.0))):
            obstacle = Cube3D(position=Vec3(x, 0.0, z), size=0.9, name=f"obstacle-{index}")
            self.obstacles.append(obstacle)
            self.collisions.add(BoxCollider3D(obstacle, tag="obstacle"))

    def _create_navigation(self) -> None:
        self.nav = NavigationGrid3D(12, 8, cell_size=1.0, origin=Vec3(), diagonal=True)
        self.nav.set_blocked_many(tuple((5, z) for z in range(8) if z != 4))
        self.agent = NavigationAgent3D(self.player, self.nav, speed=2.8, stopping_distance=0.05)
        if not self.agent.set_destination(Vec3(10.2, 0.0, 6.2)):
            raise RuntimeError("1.3 validation route could not be generated")

    def _create_streaming_world(self) -> None:
        self.streaming_scene = Scene()

        def provider(key: ChunkKey) -> ChunkDefinition:
            def build(_context) -> ChunkContent:
                marker = Cube3D(
                    position=Vec3(float(key.x), -10.0, float(key.y)),
                    size=0.1,
                    name=f"chunk-{key.x}-{key.y}",
                )
                return ChunkContent(objects=(marker,))

            return ChunkDefinition(key, build, name=f"sector-{key.x}-{key.y}")

        self.streamer = LargeWorldStreamer(
            self.streaming_scene,
            provider,
            settings=LargeWorldSettings(
                chunk_size=16.0,
                dimensions=2,
                active_radius_chunks=1,
                preload_radius_chunks=2,
                retention_radius_chunks=3,
                max_activations_per_update=4,
                max_deactivations_per_update=16,
            ),
        )

    def _pulse(self) -> None:
        self.pulses += 1

    def _update(self, dt: float) -> None:
        self.frames += 1
        self.elapsed += dt
        self.gameplay.update(dt)
        self.agent.update(dt)
        self.streamer.update((self.player.position.x * 2.0, self.player.position.z * 2.0))
        self.collisions.overlap_box(
            AABB3D(
                self.player.position.x,
                self.player.position.y,
                self.player.position.z,
                3.0,
                2.0,
                3.0,
            )
        )
        self.collision_queries += 1
        self.core.rotation.y += 45.0 * dt
        pulse = 0.55 + 0.35 * ((self.frames % 30) / 29.0)
        self.shader_material.set_uniform("pulse", pulse)

        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES:
            assert self.frames >= SMOKE_FRAMES
            assert self.instances.instance_count == 324
            assert self.streamer.diagnostics.active_chunks > 0
            assert self.nav.diagnostics.searches >= 1
            assert self.collisions.diagnostics.collider_count == 4
            assert self.collision_queries >= SMOKE_FRAMES
            print(
                "Neon Frontier 1.3 smoke OK: "
                f"frames={self.frames}, instances={self.instances.instance_count}, "
                f"active_chunks={self.streamer.diagnostics.active_chunks}, "
                f"nav_searches={self.nav.diagnostics.searches}, "
                f"collision_queries={self.collision_queries}, pulses={self.pulses}"
            )


if __name__ == "__main__":
    if os.environ.get("SWIR_DEMO_RUNTIME_PROBE") == "1":
        raise SystemExit(runtime_probe())
    NeonFrontier13().run()
