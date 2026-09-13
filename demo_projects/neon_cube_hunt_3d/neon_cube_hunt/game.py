from __future__ import annotations

import math
import os
from collections.abc import Callable

import swirengine as sw

DEMO_VERSION = "1.0.0"
ARENA_HALF = 8.0
PLAYER_SPEED = 6.0
BOOST_MULTIPLIER = 1.75
COLLECT_RADIUS = 1.05
HAZARD_RADIUS = 1.15


class NeonCubeHunt3D:
    """Small asset-free 3D game used as a real SwirEngine 1.0 validation project."""

    def __init__(self, game: sw.Game, *, smoke_frames: int = 0) -> None:
        self.game = game
        self.smoke_frames = max(0, int(smoke_frames))
        self.frame_count = 0
        self.elapsed = 0.0
        self.score = 0
        self.lives = 3
        self.wins = 0
        self.resets = 0
        self.damage_cooldown = 0.0

        self._cube = sw.cube_mesh()
        self._create_world()
        self.reset_round()

    def _mesh(
        self,
        *,
        name: str,
        position: sw.Vec3,
        scale: sw.Vec3,
        color: sw.Color,
        material: sw.Material3D,
        tags: set[str] | None = None,
    ) -> sw.Mesh3D:
        mesh = self.game.mesh(
            self._cube,
            name=name,
            color=color,
            material=material,
            tags=set() if tags is None else set(tags),
        )
        mesh.position = position
        mesh.scale = scale
        return mesh

    def _create_world(self) -> None:
        floor_material = sw.Material3D(
            tint=sw.Color(0.16, 0.19, 0.26, 1.0),
            metallic=0.15,
            roughness=0.78,
        )
        wall_material = sw.Material3D(
            tint=sw.Color(0.08, 0.18, 0.48, 1.0),
            metallic=0.5,
            roughness=0.28,
            emissive_factor=sw.Color(0.02, 0.05, 0.22, 1.0),
        )
        player_material = sw.Material3D(
            tint=sw.Color(0.18, 1.0, 0.48, 1.0),
            metallic=0.2,
            roughness=0.22,
            emissive_factor=sw.Color(0.02, 0.18, 0.06, 1.0),
        )
        collect_material = sw.Material3D(
            tint=sw.Color(1.0, 0.72, 0.08, 1.0),
            metallic=0.65,
            roughness=0.18,
            emissive_factor=sw.Color(0.28, 0.12, 0.01, 1.0),
        )
        hazard_material = sw.Material3D(
            tint=sw.Color(1.0, 0.12, 0.18, 1.0),
            metallic=0.35,
            roughness=0.3,
            emissive_factor=sw.Color(0.22, 0.01, 0.02, 1.0),
        )
        progress_material = sw.Material3D(
            tint=sw.Color(0.16, 0.95, 1.0, 1.0),
            metallic=0.4,
            roughness=0.18,
            emissive_factor=sw.Color(0.03, 0.2, 0.24, 1.0),
        )

        self.floor = self._mesh(
            name="arena-floor",
            position=sw.Vec3(0.0, -0.72, 0.0),
            scale=sw.Vec3(18.0, 0.5, 18.0),
            color=sw.Color(),
            material=floor_material,
            tags={"arena"},
        )

        wall_specs = (
            (sw.Vec3(0.0, 0.15, -9.0), sw.Vec3(18.4, 1.8, 0.35)),
            (sw.Vec3(0.0, 0.15, 9.0), sw.Vec3(18.4, 1.8, 0.35)),
            (sw.Vec3(-9.0, 0.15, 0.0), sw.Vec3(0.35, 1.8, 18.4)),
            (sw.Vec3(9.0, 0.15, 0.0), sw.Vec3(0.35, 1.8, 18.4)),
        )
        self.walls = [
            self._mesh(
                name=f"arena-wall-{index}",
                position=position,
                scale=scale,
                color=sw.Color(),
                material=wall_material,
                tags={"arena", "wall"},
            )
            for index, (position, scale) in enumerate(wall_specs)
        ]

        self.player = self._mesh(
            name="player",
            position=sw.Vec3(),
            scale=sw.Vec3(0.85, 0.85, 0.85),
            color=sw.Color(),
            material=player_material,
            tags={"player"},
        )

        collectible_positions = (
            sw.Vec3(-5.5, 0.0, -4.6),
            sw.Vec3(5.3, 0.0, -4.2),
            sw.Vec3(-4.8, 0.0, 4.5),
            sw.Vec3(5.2, 0.0, 4.2),
            sw.Vec3(0.0, 0.0, -6.5),
            sw.Vec3(0.0, 0.0, 6.4),
        )
        self.collectibles = [
            self._mesh(
                name=f"energy-core-{index + 1}",
                position=position,
                scale=sw.Vec3(0.65, 0.65, 0.65),
                color=sw.Color(),
                material=collect_material,
                tags={"collectible"},
            )
            for index, position in enumerate(collectible_positions)
        ]

        self.hazards = [
            self._mesh(
                name=f"hazard-{index + 1}",
                position=sw.Vec3(),
                scale=sw.Vec3(1.05, 1.05, 1.05),
                color=sw.Color(),
                material=hazard_material,
                tags={"hazard"},
            )
            for index in range(3)
        ]

        marker_x = -3.75
        self.progress_markers = [
            self._mesh(
                name=f"progress-{index + 1}",
                position=sw.Vec3(marker_x + index * 1.5, 1.0, -8.55),
                scale=sw.Vec3(0.45, 1.3, 0.32),
                color=sw.Color(),
                material=progress_material,
                tags={"progress"},
            )
            for index in range(len(self.collectibles))
        ]

        self.game.directional_light(
            direction=sw.Vec3(-0.62, -1.0, -0.38),
            color=sw.Color(1.0, 0.9, 0.76, 1.0),
            intensity=2.2,
        )
        self.game.point_light(
            position=sw.Vec3(-6.0, 3.4, -5.5),
            color=sw.Color(0.08, 0.4, 1.0, 1.0),
            intensity=9.0,
            range=12.0,
        )
        self.game.point_light(
            position=sw.Vec3(6.0, 3.0, 5.5),
            color=sw.Color(1.0, 0.08, 0.28, 1.0),
            intensity=8.0,
            range=12.0,
        )

    @staticmethod
    def _distance_sq(a: sw.Vec3, b: sw.Vec3) -> float:
        dx = a.x - b.x
        dy = a.y - b.y
        dz = a.z - b.z
        return dx * dx + dy * dy + dz * dz

    def reset_round(self) -> None:
        self.score = 0
        self.lives = 3
        self.damage_cooldown = 0.0
        self.player.position = sw.Vec3(0.0, 0.0, 0.0)
        self.player.rotation = sw.Vec3()
        for collectible in self.collectibles:
            collectible.visible = True
        for marker in self.progress_markers:
            marker.visible = False
        self._update_camera()

    def _update_camera(self) -> None:
        focus = self.player.position
        self.game.camera.position = focus + sw.Vec3(9.5, 8.0, 10.5)
        self.game.camera.look_at(focus + sw.Vec3(0.0, -0.15, 0.0))

    def _move_player(self, dt: float, pressed: Callable[[str], bool]) -> None:
        x_axis = float(pressed("d")) - float(pressed("a"))
        z_axis = float(pressed("s")) - float(pressed("w"))
        length = math.hypot(x_axis, z_axis)
        if length > 0.0:
            x_axis /= length
            z_axis /= length
            speed = PLAYER_SPEED * (BOOST_MULTIPLIER if pressed("space") else 1.0)
            self.player.position.x += x_axis * speed * dt
            self.player.position.z += z_axis * speed * dt
            self.player.rotation.y = math.degrees(math.atan2(x_axis, -z_axis))
        self.player.position.x = max(-ARENA_HALF, min(ARENA_HALF, self.player.position.x))
        self.player.position.z = max(-ARENA_HALF, min(ARENA_HALF, self.player.position.z))

    def _animate_world(self, dt: float) -> None:
        self.elapsed += dt
        for index, collectible in enumerate(self.collectibles):
            collectible.rotation.y += (45.0 + index * 7.0) * dt
            collectible.position.y = 0.15 + math.sin(self.elapsed * 2.4 + index) * 0.18

        patterns = (
            (5.4, 0.82, 0.0),
            (4.2, -1.08, 2.1),
            (6.1, 0.61, 4.2),
        )
        for hazard, (radius, speed, phase) in zip(self.hazards, patterns, strict=True):
            angle = self.elapsed * speed + phase
            hazard.position.x = math.sin(angle) * radius
            hazard.position.z = math.cos(angle * 0.87) * radius
            hazard.position.y = 0.02
            hazard.rotation.x += 55.0 * dt
            hazard.rotation.y += 80.0 * dt

    def _collect(self) -> None:
        radius_sq = COLLECT_RADIUS * COLLECT_RADIUS
        for collectible in self.collectibles:
            if not collectible.visible:
                continue
            if self._distance_sq(self.player.position, collectible.position) <= radius_sq:
                collectible.visible = False
                self.score += 1
                self.progress_markers[self.score - 1].visible = True

        if self.score == len(self.collectibles):
            self.wins += 1
            self.reset_round()

    def _handle_hazards(self) -> None:
        self.damage_cooldown = max(0.0, self.damage_cooldown)
        if self.damage_cooldown > 0.0:
            return
        radius_sq = HAZARD_RADIUS * HAZARD_RADIUS
        if not any(
            self._distance_sq(self.player.position, hazard.position) <= radius_sq
            for hazard in self.hazards
        ):
            return
        self.lives -= 1
        self.damage_cooldown = 0.85
        self.player.position = sw.Vec3()
        if self.lives <= 0:
            self.resets += 1
            self.reset_round()

    def step(
        self,
        dt: float,
        pressed: Callable[[str], bool] | None = None,
    ) -> None:
        """Advance gameplay without requiring a window; useful for tests and editor tooling."""

        delta = max(0.0, min(float(dt), 0.1))
        key = self.game.key if pressed is None else pressed
        self.damage_cooldown = max(0.0, self.damage_cooldown - delta)
        self._move_player(delta, key)
        self._animate_world(delta)
        self._collect()
        self._handle_hazards()
        self._update_camera()

        self.frame_count += 1
        if self.smoke_frames and self.frame_count >= self.smoke_frames:
            self.game.stop()


def create_demo_game(*, smoke_frames: int = 0) -> tuple[sw.Game, NeonCubeHunt3D]:
    """Build the complete demo using only public SwirEngine 1.x APIs."""

    game = sw.Game(
        "Neon Cube Hunt 3D - SwirEngine 1.0",
        width=1280,
        height=720,
        mode="3d",
        target_fps=120,
    )
    game.configure_postprocess(
        enabled=True,
        tone_mapping="aces",
        exposure=1.08,
        contrast=1.06,
        saturation=1.12,
        vignette=0.16,
        fxaa=True,
    )
    game.configure_shadows(
        enabled=True,
        resolution=1024,
        extent=18.0,
        distance=28.0,
        near=0.1,
        far=65.0,
        bias=0.0016,
        normal_bias=0.0035,
    )

    demo = NeonCubeHunt3D(game, smoke_frames=smoke_frames)

    @game.update
    def update(dt: float) -> None:
        if game.key_pressed("escape"):
            game.stop()
            return
        if game.key_pressed("r"):
            demo.resets += 1
            demo.reset_round()
        demo.step(dt)

    return game, demo


def main() -> None:
    smoke_frames = int(os.environ.get("SWIR_DEMO_SMOKE_FRAMES", "0") or 0)
    game, _demo = create_demo_game(smoke_frames=smoke_frames)
    print("Neon Cube Hunt 3D")
    print("WASD: move | SPACE: boost | R: reset | ESC: quit")
    game.run()


if __name__ == "__main__":
    main()
