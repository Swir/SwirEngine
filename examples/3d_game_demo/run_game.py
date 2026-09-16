"""SwirEngine 3D Game Demo — an asset-free classic corridor FPS showcase.

The demo is inspired by the feel of early fast-paced first-person shooters while using an original
layout, generated geometry, colors, gameplay code, and no third-party game assets.

Run from the repository root:
    python examples/3d_game_demo/run_game.py

Controls:
    W / A / S / D         Move
    Mouse / arrow keys    Look
    Left mouse / Space    Fire
    Left Shift            Sprint
    R                     Restart
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt

from swirengine import Color, Cube3D, Game, Renderer2Settings, Vec3
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.mesh import Mesh3D, cube_mesh

WIDTH = 960
HEIGHT = 540
SMOKE_FRAMES = int(os.environ.get("SWIR_GAME_DEMO_SMOKE_FRAMES", "0"))
HEADLESS = os.environ.get("SWIR_GAME_DEMO_HEADLESS") == "1"
FIXED_DT = 1.0 / 120.0
PLAYER_RADIUS = 0.32

# Keep the live Renderer 2.0 settings in one shared mapping. The headless probe constructs
# Renderer2Settings from this same mapping so invalid quality values fail before the OpenGL smoke job.
RENDERER2_OPTIONS: dict[str, object] = {
    "shadow_cascades": 3,
    "shadow_resolution": 1024,
    "shadow_distance": 80.0,
    "ssao": True,
    "ssao_samples": 16,
    "bloom": True,
    "bloom_levels": 4,
    "decals": True,
    "max_decals": 32,
    "hdr": True,
}


@dataclass(frozen=True, slots=True)
class Wall:
    x: float
    z: float
    width: float
    depth: float

    @property
    def left(self) -> float:
        return self.x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width / 2.0

    @property
    def near(self) -> float:
        return self.z - self.depth / 2.0

    @property
    def far(self) -> float:
        return self.z + self.depth / 2.0


@dataclass(slots=True)
class Enemy:
    x: float
    z: float
    hp: int = 3
    attack_cooldown: float = 0.0

    @property
    def alive(self) -> bool:
        return self.hp > 0


@dataclass(slots=True)
class Pickup:
    x: float
    z: float
    kind: str
    active: bool = True


WALLS = (
    Wall(-9.5, -5.0, 1.0, 30.0),
    Wall(9.5, -5.0, 1.0, 30.0),
    Wall(0.0, 9.5, 20.0, 1.0),
    Wall(0.0, -19.5, 20.0, 1.0),
    Wall(-3.5, -6.5, 0.8, 9.0),
    Wall(3.5, -10.0, 0.8, 9.0),
    Wall(0.0, -14.5, 6.0, 0.8),
    Wall(-6.5, -1.0, 5.2, 0.8),
    Wall(6.5, -4.0, 5.2, 0.8),
)
SPAWN_X = 0.0
SPAWN_Z = 7.0
EXIT_X = 7.2
EXIT_Z = -18.1


def _distance(x0: float, z0: float, x1: float, z1: float) -> float:
    dx = x1 - x0
    dz = z1 - z0
    return sqrt(dx * dx + dz * dz)


def _point_blocked(x: float, z: float, radius: float = PLAYER_RADIUS) -> bool:
    for wall in WALLS:
        if (
            wall.left - radius < x < wall.right + radius
            and wall.near - radius < z < wall.far + radius
        ):
            return True
    return False


def _segment_hits_wall(x0: float, z0: float, x1: float, z1: float) -> bool:
    """Return whether a 2D X/Z segment crosses any wall using a slab intersection test."""
    dx = x1 - x0
    dz = z1 - z0
    for wall in WALLS:
        t_min = 0.0
        t_max = 1.0
        for origin, delta, low, high in (
            (x0, dx, wall.left, wall.right),
            (z0, dz, wall.near, wall.far),
        ):
            if abs(delta) < 1e-9:
                if origin < low or origin > high:
                    break
                continue
            inv = 1.0 / delta
            near_t = (low - origin) * inv
            far_t = (high - origin) * inv
            if near_t > far_t:
                near_t, far_t = far_t, near_t
            t_min = max(t_min, near_t)
            t_max = min(t_max, far_t)
            if t_min > t_max:
                break
        else:
            if 0.001 < t_max and t_min < 0.999:
                return True
    return False


class FPSState:
    """Deterministic gameplay model used by both the rendered example and CI validation."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.x = SPAWN_X
        self.z = SPAWN_Z
        self.yaw = 0.0
        self.pitch = 0.0
        self.health = 100
        self.ammo = 18
        self.kills = 0
        self.won = False
        self.lost = False
        self.enemies = [
            Enemy(0.0, 2.0),
            Enemy(-6.2, -8.0),
            Enemy(6.2, -14.0),
        ]
        self.pickups = [
            Pickup(-6.5, -4.8, "ammo"),
            Pickup(6.3, -9.0, "health"),
        ]

    @property
    def forward(self) -> tuple[float, float]:
        return sin(self.yaw), -cos(self.yaw)

    @property
    def right(self) -> tuple[float, float]:
        return cos(self.yaw), sin(self.yaw)

    def look(self, dx: float, dy: float, *, sensitivity: float = 0.0025) -> None:
        self.yaw += float(dx) * sensitivity
        self.pitch -= float(dy) * sensitivity
        limit = radians(82.0)
        self.pitch = max(-limit, min(limit, self.pitch))

    def look_at(self, x: float, z: float) -> None:
        self.yaw = atan2(x - self.x, -(z - self.z))
        self.pitch = 0.0

    def _try_move(self, dx: float, dz: float) -> None:
        candidate_x = self.x + dx
        if not _point_blocked(candidate_x, self.z):
            self.x = candidate_x
        candidate_z = self.z + dz
        if not _point_blocked(self.x, candidate_z):
            self.z = candidate_z

    def shoot(self) -> bool:
        if self.won or self.lost or self.ammo <= 0:
            return False
        self.ammo -= 1
        forward_x, forward_z = self.forward
        hit: Enemy | None = None
        hit_distance = 1e9
        threshold = cos(radians(9.0))

        for enemy in self.enemies:
            if not enemy.alive:
                continue
            dx = enemy.x - self.x
            dz = enemy.z - self.z
            distance = sqrt(dx * dx + dz * dz)
            if distance <= 0.001 or distance > 22.0:
                continue
            dot = (dx / distance) * forward_x + (dz / distance) * forward_z
            if dot < threshold or _segment_hits_wall(self.x, self.z, enemy.x, enemy.z):
                continue
            if distance < hit_distance:
                hit = enemy
                hit_distance = distance

        if hit is None:
            return False
        hit.hp -= 1
        if hit.hp <= 0:
            self.kills += 1
        return True

    def _update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            enemy.attack_cooldown = max(0.0, enemy.attack_cooldown - dt)
            dx = self.x - enemy.x
            dz = self.z - enemy.z
            distance = sqrt(dx * dx + dz * dz)
            if distance <= 0.001 or distance > 12.0:
                continue
            if _segment_hits_wall(enemy.x, enemy.z, self.x, self.z):
                continue

            if distance > 1.6:
                step = min(1.35 * dt, max(0.0, distance - 1.45))
                next_x = enemy.x + dx / distance * step
                next_z = enemy.z + dz / distance * step
                if not _point_blocked(next_x, next_z, 0.28):
                    enemy.x = next_x
                    enemy.z = next_z
            elif enemy.attack_cooldown <= 0.0:
                self.health = max(0, self.health - 12)
                enemy.attack_cooldown = 0.65
                if self.health <= 0:
                    self.lost = True
                    return

    def _collect_pickups(self) -> None:
        for pickup in self.pickups:
            if not pickup.active or _distance(self.x, self.z, pickup.x, pickup.z) > 0.8:
                continue
            pickup.active = False
            if pickup.kind == "ammo":
                self.ammo = min(36, self.ammo + 12)
            elif pickup.kind == "health":
                self.health = min(100, self.health + 35)

    def step(self, move_x: float, move_z: float, sprint: bool, dt: float) -> None:
        if self.won or self.lost:
            return
        dt = max(0.0, min(float(dt), 1.0 / 20.0))
        move_x = max(-1.0, min(1.0, float(move_x)))
        move_z = max(-1.0, min(1.0, float(move_z)))
        length = sqrt(move_x * move_x + move_z * move_z)
        if length > 1.0:
            move_x /= length
            move_z /= length

        forward_x, forward_z = self.forward
        right_x, right_z = self.right
        speed = 6.0 if sprint else 4.2
        dx = (right_x * move_x + forward_x * move_z) * speed * dt
        dz = (right_z * move_x + forward_z * move_z) * speed * dt
        self._try_move(dx, dz)
        self._update_enemies(dt)
        self._collect_pickups()

        if all(not enemy.alive for enemy in self.enemies) and _distance(
            self.x, self.z, EXIT_X, EXIT_Z
        ) < 1.2:
            self.won = True


def run_headless_probe() -> dict[str, int | float | bool]:
    renderer_settings = Renderer2Settings(**RENDERER2_OPTIONS)
    if renderer_settings.ssao_samples != 16:
        raise AssertionError("3D demo Renderer 2.0 quality configuration drifted")

    state = FPSState()
    start_z = state.z
    for _ in range(30):
        state.step(0.0, 1.0, False, FIXED_DT)
    if state.z >= start_z - 0.5:
        raise AssertionError("3D demo first-person movement did not advance")

    first = state.enemies[0]
    state.x = 0.0
    state.z = 7.0
    state.look_at(first.x, first.z)
    ammo_before = state.ammo
    hits = 0
    for _ in range(3):
        hits += int(state.shoot())
    if hits != 3 or first.alive or state.kills != 1 or state.ammo != ammo_before - 3:
        raise AssertionError("3D demo shooting/damage loop did not defeat the target")

    ammo_pickup = state.pickups[0]
    state.ammo = 4
    state.x = ammo_pickup.x
    state.z = ammo_pickup.z
    state.step(0.0, 0.0, False, FIXED_DT)
    if ammo_pickup.active or state.ammo <= 4:
        raise AssertionError("3D demo ammo pickup did not apply")

    for enemy in state.enemies:
        enemy.hp = 0
    state.kills = len(state.enemies)
    state.x = EXIT_X
    state.z = EXIT_Z
    state.step(0.0, 0.0, False, FIXED_DT)
    if not state.won:
        raise AssertionError("3D demo exit did not unlock after all enemies were defeated")

    return {
        "movement": round(start_z - state.enemies[0].z, 3),
        "kills": state.kills,
        "ammo": state.ammo,
        "health": state.health,
        "won": state.won,
    }


class FPSDemo:
    def __init__(self) -> None:
        self.game = Game(
            "SwirEngine 3D Game Demo",
            WIDTH,
            HEIGHT,
            mode="3d",
            vsync=False,
            target_fps=144,
        )
        self.game.configure_renderer2(True, **RENDERER2_OPTIONS)
        self.game.configure_postprocess(
            enabled=True,
            tone_mapping="aces",
            exposure=1.05,
            fxaa=True,
        )
        self.state = FPSState()
        self.frames = 0
        self._shot_flash = 0.0

        camera = self.game.camera
        if not isinstance(camera, Camera3D):
            raise TypeError("3D game demo requires Camera3D")
        camera.fov = 74.0
        self.camera = camera

        cube = cube_mesh()
        self.game.add(
            Mesh3D(
                cube,
                position=Vec3(0.0, -0.25, -5.0),
                scale=Vec3(20.0, 0.5, 30.0),
                color=Color(0.055, 0.065, 0.085, 1.0),
                name="arena-floor",
            )
        )
        self.game.add(
            Mesh3D(
                cube,
                position=Vec3(0.0, 3.8, -5.0),
                scale=Vec3(20.0, 0.2, 30.0),
                color=Color(0.035, 0.04, 0.055, 1.0),
                name="arena-ceiling",
            )
        )
        for index, wall in enumerate(WALLS):
            self.game.add(
                Mesh3D(
                    cube,
                    position=Vec3(wall.x, 1.7, wall.z),
                    scale=Vec3(wall.width, 3.4, wall.depth),
                    color=Color(
                        0.09 + (index % 3) * 0.015,
                        0.14 + (index % 2) * 0.025,
                        0.22 + (index % 4) * 0.02,
                        1.0,
                    ),
                    name=f"wall-{index}",
                    tags={"wall"},
                )
            )

        self.exit_node = self.game.add(
            Mesh3D(
                cube,
                position=Vec3(EXIT_X, 1.2, EXIT_Z),
                scale=Vec3(1.5, 2.4, 0.25),
                color=Color(0.18, 0.28, 0.3, 1.0),
                name="exit-gate",
            )
        )
        self.enemy_nodes = [
            self.game.add(
                Cube3D(
                    position=Vec3(enemy.x, 0.55, enemy.z),
                    size=1.05,
                    color=Color(1.0, 0.18, 0.28, 1.0),
                    name=f"enemy-{index}",
                    tags={"enemy"},
                    visibility_dynamic=True,
                )
            )
            for index, enemy in enumerate(self.state.enemies)
        ]
        self.pickup_nodes = [
            self.game.add(
                Cube3D(
                    position=Vec3(pickup.x, 0.4, pickup.z),
                    size=0.45,
                    color=(
                        Color(1.0, 0.72, 0.12, 1.0)
                        if pickup.kind == "ammo"
                        else Color(0.15, 1.0, 0.42, 1.0)
                    ),
                    name=f"{pickup.kind}-pickup-{index}",
                    tags={"pickup"},
                    visibility_dynamic=True,
                )
            )
            for index, pickup in enumerate(self.state.pickups)
        ]
        self.weapon = self.game.add(
            Cube3D(
                position=Vec3(),
                size=0.28,
                color=Color(0.15, 0.55, 0.75, 1.0),
                name="player-weapon",
                visibility_dynamic=True,
            )
        )

        self.game.directional_light(
            direction=Vec3(-0.5, -1.0, -0.35),
            intensity=1.35,
        )
        self.game.point_light(
            position=Vec3(-6.5, 2.2, -4.8),
            color=Color(0.2, 0.55, 1.0, 1.0),
            intensity=9.0,
            range=8.0,
        )
        self.game.point_light(
            position=Vec3(6.3, 2.1, -9.0),
            color=Color(0.15, 1.0, 0.42, 1.0),
            intensity=8.0,
            range=7.0,
        )
        self.game.point_light(
            position=Vec3(EXIT_X, 2.0, EXIT_Z),
            color=Color(0.2, 0.9, 1.0, 1.0),
            intensity=10.0,
            range=7.0,
        )

        self.hud = self.game.label("", -350.0, 238.0, font_size=20)
        self.objective = self.game.label("", 190.0, 238.0, font_size=18)
        self.crosshair = self.game.label("+", 0.0, 0.0, font_size=28)
        self.help = self.game.label(
            "WASD move | mouse/arrows look | click/SPACE fire | SHIFT sprint | R restart",
            0.0,
            -252.0,
            font_size=15,
        )

        self.game.update(self._update)
        self._sync_visuals()

    def _sync_camera(self) -> None:
        horizontal = cos(self.state.pitch)
        direction = Vec3(
            sin(self.state.yaw) * horizontal,
            sin(self.state.pitch),
            -cos(self.state.yaw) * horizontal,
        )
        self.camera.position = Vec3(self.state.x, 1.62, self.state.z)
        self.camera.look_at(self.camera.position + direction)

        forward = self.camera.forward
        right = self.camera.right
        self.weapon.position = (
            self.camera.position
            + forward * 0.65
            + right * 0.28
            + Vec3(0.0, -0.28, 0.0)
        )
        self.weapon.color = (
            Color(1.0, 0.72, 0.2, 1.0)
            if self._shot_flash > 0.0
            else Color(0.15, 0.55, 0.75, 1.0)
        )

    def _sync_visuals(self) -> None:
        self._sync_camera()
        for node, enemy in zip(self.enemy_nodes, self.state.enemies, strict=True):
            node.position = Vec3(enemy.x, 0.55, enemy.z)
            node.visible = enemy.alive
            node.color = (
                Color(1.0, 0.18, 0.28, 1.0)
                if enemy.hp >= 2
                else Color(1.0, 0.55, 0.18, 1.0)
            )
        for node, pickup in zip(self.pickup_nodes, self.state.pickups, strict=True):
            node.visible = pickup.active
            node.rotation.y += 1.5

        unlocked = all(not enemy.alive for enemy in self.state.enemies)
        self.exit_node.color = (
            Color(0.1, 1.0, 0.45, 1.0) if unlocked else Color(0.18, 0.28, 0.3, 1.0)
        )
        self.hud.text = (
            f"HP {self.state.health:03d}   AMMO {self.state.ammo:02d}   "
            f"KILLS {self.state.kills}/3"
        )
        if self.state.won:
            self.objective.text = "SECTOR CLEAR - press R to restart"
        elif self.state.lost:
            self.objective.text = "YOU ARE DOWN - press R to restart"
        elif unlocked:
            self.objective.text = "Exit unlocked - reach the green gate"
        else:
            self.objective.text = "Clear the arena"

    def _update(self, dt: float) -> None:
        self.frames += 1
        self._shot_flash = max(0.0, self._shot_flash - dt)
        if self.game.key_pressed("R"):
            self.state.reset()

        mouse_dx = max(-40.0, min(40.0, self.game.input.mouse_dx))
        mouse_dy = max(-40.0, min(40.0, self.game.input.mouse_dy))
        keyboard_dx = 0.0
        keyboard_dy = 0.0
        if self.game.key("LEFT"):
            keyboard_dx -= 130.0 * dt
        if self.game.key("RIGHT"):
            keyboard_dx += 130.0 * dt
        if self.game.key("UP"):
            keyboard_dy -= 110.0 * dt
        if self.game.key("DOWN"):
            keyboard_dy += 110.0 * dt
        self.state.look(mouse_dx + keyboard_dx, mouse_dy + keyboard_dy)

        move_x = 0.0
        move_z = 0.0
        if self.game.key("A"):
            move_x -= 1.0
        if self.game.key("D"):
            move_x += 1.0
        if self.game.key("W"):
            move_z += 1.0
        if self.game.key("S"):
            move_z -= 1.0
        sprint = self.game.key("LEFT_SHIFT") or self.game.key("RIGHT_SHIFT")
        self.state.step(move_x, move_z, sprint, dt)

        if self.game.input.mouse_button_pressed(0) or self.game.key_pressed("SPACE"):
            self.state.shoot()
            self._shot_flash = 0.08

        self._sync_visuals()
        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES and self.frames < SMOKE_FRAMES:
            raise AssertionError("3D game demo stopped before the requested smoke frame count")
        if SMOKE_FRAMES:
            print(
                "SwirEngine 3D Game Demo smoke OK: "
                f"frames={self.frames}, hp={self.state.health}, ammo={self.state.ammo}, "
                f"kills={self.state.kills}"
            )


def main() -> int:
    if HEADLESS:
        diagnostics = run_headless_probe()
        print(f"SwirEngine 3D Game Demo headless OK: {diagnostics}")
        return 0
    FPSDemo().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
