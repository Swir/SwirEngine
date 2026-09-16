"""SwirEngine 3D Game Demo — engine-driven, source-only mini FPS showcase."""

from __future__ import annotations

import math
import os

from procedural_art import ensure_art

from swirengine import (
    CharacterConfig3D,
    CharacterInput3D,
    Color,
    Cube3D,
    FirstPersonController3D,
    Game,
    Renderer2Settings,
    Vec3,
)
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.material import Material3D
from swirengine.graphics.mesh import Mesh3D, cube_mesh
from swirengine.physics.collision3d import BoxCollider3D, SphereBounds3D
from swirengine.physics.dynamics3d import PhysicsBody3D, PhysicsScene3D

W, H = 960, 540
FIXED_DT = 1.0 / 120.0
SMOKE_FRAMES = int(os.environ.get("SWIR_GAME_DEMO_SMOKE_FRAMES", "0"))
HEADLESS = os.environ.get("SWIR_GAME_DEMO_HEADLESS") == "1"
WORLD, PLAYER, ENEMY = 1, 2, 4
SPAWN = Vec3(0.0, 0.92, 8.5)
EXIT = Vec3(8.2, 0.0, -21.6)
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

BLOCKS = (
    (0.0, -0.25, -6.0, 22.0, 0.5, 34.0, "floor"),
    (-10.75, 1.7, -6.0, 0.5, 3.9, 34.0, "wall"),
    (10.75, 1.7, -6.0, 0.5, 3.9, 34.0, "wall"),
    (0.0, 1.7, 10.75, 22.0, 3.9, 0.5, "wall"),
    (0.0, 1.7, -22.75, 22.0, 3.9, 0.5, "wall"),
    (-4.8, 1.3, 3.0, 0.7, 2.6, 10.0, "wall"),
    (4.2, 1.3, -1.5, 0.7, 2.6, 9.0, "wall"),
    (-1.2, 1.3, -7.5, 7.0, 2.6, 0.7, "wall"),
    (5.8, 0.75, -12.5, 2.2, 1.5, 2.2, "crate"),
    (-6.7, 0.75, -13.8, 2.0, 1.5, 2.0, "crate"),
    (1.6, 0.55, 5.5, 2.6, 1.1, 1.6, "panel"),
)
ENEMY_SPECS = (
    (0.0, 4.5, 2.0),
    (-7.4, -2.0, 2.7),
    (7.2, -6.5, 2.2),
    (-5.8, -16.4, 2.6),
    (5.8, -18.0, 2.4),
)
PICKUPS = (
    (-7.8, 4.2, "ammo"),
    (7.8, 1.0, "health"),
    (0.0, -11.0, "ammo"),
    (-2.8, -19.0, "health"),
)


def dist_xz(a: Vec3, b: Vec3) -> float:
    return math.hypot(a.x - b.x, a.z - b.z)


def add_static(
    world: PhysicsScene3D,
    target: object,
    size: tuple[float, float, float],
    tag: str,
) -> None:
    collider = BoxCollider3D(
        target,
        width=size[0],
        height=size[1],
        depth=size[2],
        layer=WORLD,
        mask=PLAYER | ENEMY,
        tag=tag,
    )
    world.add(PhysicsBody3D(target, collider, body_type="static"))


def run_headless_probe() -> dict[str, float | bool]:
    settings = Renderer2Settings(**RENDERER2_OPTIONS)
    if settings.ssao_samples != 16:
        raise AssertionError("3D demo Renderer 2.0 configuration drifted")

    world = PhysicsScene3D(fixed_dt=FIXED_DT)
    floor = Cube3D(position=Vec3(0, -0.25, 0), visible=False)
    wall = Cube3D(position=Vec3(4, 1.5, -2), visible=False)
    add_static(world, floor, (20, 0.5, 24), "world:floor")
    add_static(world, wall, (0.6, 3, 8), "world:wall")

    player = Cube3D(position=Vec3(0, 0.92, 4), visible=False)
    collider = BoxCollider3D(
        player, width=0.72, height=1.8, depth=0.72, layer=PLAYER, mask=WORLD, tag="player"
    )
    camera = Camera3D()
    controller = FirstPersonController3D(
        player,
        world,
        camera,
        config=CharacterConfig3D(
            width=0.72,
            height=1.8,
            depth=0.72,
            walk_speed=4.8,
            sprint_speed=7.4,
            gravity=24,
            jump_speed=7.4,
            collision_mask=WORLD,
        ),
        collider=collider,
        eye_height=0.70,
        look_sensitivity=100,
    )
    start_z = player.position.z
    for _ in range(90):
        controller.update(CharacterInput3D(move_z=1), FIXED_DT)
    movement = start_z - player.position.z
    if movement < 2:
        raise AssertionError("FirstPersonController3D did not move the demo player")

    target = Cube3D(position=Vec3(player.position.x, 0.72, player.position.z - 5), visible=False)
    target_collider = BoxCollider3D(
        target,
        width=0.82,
        height=1.85,
        depth=0.82,
        offset=Vec3(0, 0.22, 0),
        layer=ENEMY,
        mask=0,
        tag="enemy:probe",
    )
    world.add(PhysicsBody3D(target, target_collider, body_type="kinematic"))
    controller.update(CharacterInput3D(), FIXED_DT)
    hit = world.sweep_sphere(
        SphereBounds3D(camera.position.x, camera.position.y, camera.position.z, 0.03),
        camera.forward * 12,
        mask=WORLD | ENEMY,
        ignore=collider,
    )
    if hit is None or hit.collider.tag != "enemy:probe":
        raise AssertionError("PhysicsScene3D weapon sweep did not hit the enemy")
    return {
        "movement": round(movement, 3),
        "grounded": controller.state.grounded,
        "weapon_hit": True,
        "engine_controller": True,
    }


class FPSDemo:
    def __init__(self) -> None:
        self.game = Game(
            "SwirEngine 3D Game Demo", W, H, mode="3d", vsync=False, target_fps=144
        )
        self.game.configure_renderer2(True, **RENDERER2_OPTIONS)
        self.game.configure_postprocess(
            enabled=True, tone_mapping="aces", exposure=1.06, fxaa=True
        )
        camera = self.game.camera
        if not isinstance(camera, Camera3D):
            raise TypeError("3D game demo requires Camera3D")
        self.camera = camera
        self.camera.fov = 76
        self.cube = cube_mesh()
        self.art = ensure_art()
        self.audio_enabled = True
        self.materials = {
            "steel": Material3D(
                texture=self.art["steel"], metallic=0.55, roughness=0.58
            ),
            "floor": Material3D(
                texture=self.art["floor"], metallic=0.18, roughness=0.82
            ),
            "hazard": Material3D(
                texture=self.art["hazard"], metallic=0.10, roughness=0.72
            ),
            "panel": Material3D(
                texture=self.art["panel"], metallic=0.35, roughness=0.48
            ),
        }
        self.world = PhysicsScene3D(fixed_dt=FIXED_DT, max_substeps=8, cell_size=3)
        self.frames = 0
        self.phase = 0.0
        self._build_world()
        self._build_player()
        self._build_enemies()
        self._build_pickups()
        self._build_weapon_and_ui()
        self._reset()
        self.game.update(self._update)

    def mesh(
        self,
        position: Vec3,
        scale: Vec3,
        color: Color,
        name: str,
        *,
        dynamic: bool = False,
        material: Material3D | None = None,
    ) -> Mesh3D:
        return self.game.add(
            Mesh3D(
                self.cube,
                position=position,
                scale=scale,
                color=color,
                material=material,
                name=name,
                visibility_dynamic=dynamic,
            )
        )

    def _build_world(self) -> None:
        for index, (x, y, z, sx, sy, sz, kind) in enumerate(BLOCKS):
            material = self.materials["floor" if kind == "floor" else "steel"]
            if kind == "panel":
                material = self.materials["panel"]
            color = Color(0.17, 0.20, 0.23, 1) if kind == "floor" else Color(0.32, 0.39, 0.46, 1)
            node = self.mesh(
                Vec3(x, y, z),
                Vec3(sx, sy, sz),
                color,
                f"bunker-{kind}-{index}",
                material=material,
            )
            add_static(self.world, node, (sx, sy, sz), f"world:{kind}:{index}")

        for z in range(-20, 10, 4):
            self.mesh(
                Vec3(-10.42, 2.65, z),
                Vec3(0.12, 0.18, 2),
                Color(0.12, 0.70, 1, 1),
                f"blue-trim-{z}",
            )
            self.mesh(
                Vec3(10.42, 2.65, z),
                Vec3(0.12, 0.18, 2),
                Color(0.94, 0.10, 0.24, 1),
                f"red-trim-{z}",
            )

        for i, (x, z) in enumerate(((-8.5, 6.5), (8.5, 4), (-8.5, -8), (8.5, -15))):
            self.mesh(
                Vec3(x, 1.25, z),
                Vec3(0.55, 2.5, 0.55),
                Color(0.35, 0.50, 0.60, 1),
                f"pylon-{i}",
                material=self.materials["panel"],
            )
            self.mesh(
                Vec3(x, 2.25, z),
                Vec3(0.72, 0.18, 0.72),
                Color(0.18, 0.72, 1, 1),
                f"pylon-light-{i}",
            )

        self.mesh(
            Vec3(EXIT.x - 1, 1.2, EXIT.z),
            Vec3(0.45, 2.4, 0.35),
            Color(0.95, 0.80, 0.30, 1),
            "exit-left",
            material=self.materials["hazard"],
        )
        self.mesh(
            Vec3(EXIT.x + 1, 1.2, EXIT.z),
            Vec3(0.45, 2.4, 0.35),
            Color(0.95, 0.80, 0.30, 1),
            "exit-right",
            material=self.materials["hazard"],
        )
        self.exit_core = self.mesh(
            Vec3(EXIT.x, 1.25, EXIT.z),
            Vec3(1.45, 2.25, 0.22),
            Color(0.25, 0.08, 0.10, 1),
            "exit-core",
            dynamic=True,
        )

    def _build_player(self) -> None:
        self.player = self.game.add(
            Cube3D(
                position=Vec3(SPAWN.x, SPAWN.y, SPAWN.z),
                size=0.72,
                visible=False,
                name="player-root",
            )
        )
        self.player_collider = BoxCollider3D(
            self.player,
            width=0.72,
            height=1.8,
            depth=0.72,
            layer=PLAYER,
            mask=WORLD,
            tag="player",
        )
        self.controller = FirstPersonController3D(
            self.player,
            self.world,
            self.camera,
            config=CharacterConfig3D(
                width=0.72,
                height=1.8,
                depth=0.72,
                walk_speed=4.8,
                sprint_speed=7.4,
                ground_acceleration=44,
                air_acceleration=12,
                gravity=24,
                jump_speed=7.3,
                step_height=0.35,
                ground_snap_distance=0.14,
                collision_mask=WORLD,
            ),
            collider=self.player_collider,
            eye_height=0.70,
            look_sensitivity=105,
        )

    def _build_enemies(self) -> None:
        self.enemies: list[dict[str, object]] = []
        for i, (x, z, patrol) in enumerate(ENEMY_SPECS):
            root = self.game.add(
                Cube3D(
                    position=Vec3(x, 0.72, z),
                    size=0.8,
                    visible=False,
                    name=f"enemy-root-{i}",
                )
            )
            collider = BoxCollider3D(
                root,
                width=0.82,
                height=1.85,
                depth=0.82,
                offset=Vec3(0, 0.22, 0),
                layer=ENEMY,
                mask=0,
                tag=f"enemy:{i}",
            )
            body = self.world.add(PhysicsBody3D(root, collider, body_type="kinematic"))
            visual = [
                self.mesh(Vec3(), Vec3(0.72, 0.82, 0.46), Color(0.70, 0.08, 0.16, 1), f"e{i}-body", dynamic=True),
                self.mesh(Vec3(), Vec3(0.62, 0.46, 0.54), Color(0.94, 0.20, 0.24, 1), f"e{i}-head", dynamic=True),
                self.mesh(Vec3(), Vec3(0.36, 0.08, 0.06), Color(1, 0.72, 0.12, 1), f"e{i}-eye", dynamic=True),
                self.mesh(Vec3(), Vec3(0.16, 0.62, 0.18), Color(0.45, 0.05, 0.11, 1), f"e{i}-arm-l", dynamic=True),
                self.mesh(Vec3(), Vec3(0.16, 0.62, 0.18), Color(0.45, 0.05, 0.11, 1), f"e{i}-arm-r", dynamic=True),
                self.mesh(Vec3(), Vec3(0.20, 0.42, 0.20), Color(0.28, 0.04, 0.08, 1), f"e{i}-leg-l", dynamic=True),
                self.mesh(Vec3(), Vec3(0.20, 0.42, 0.20), Color(0.28, 0.04, 0.08, 1), f"e{i}-leg-r", dynamic=True),
            ]
            self.enemies.append(
                {
                    "root": root,
                    "collider": collider,
                    "body": body,
                    "visual": visual,
                    "origin": Vec3(x, 0.72, z),
                    "patrol": patrol,
                    "hp": 4,
                    "alive": True,
                    "cooldown": 0.0,
                    "flash": 0.0,
                    "phase": i * 1.1,
                }
            )

    def _build_pickups(self) -> None:
        self.pickups: list[dict[str, object]] = []
        for i, (x, z, kind) in enumerate(PICKUPS):
            color = Color(1, 0.62, 0.08, 1) if kind == "ammo" else Color(0.10, 1, 0.48, 1)
            core = self.mesh(
                Vec3(x, 0.48, z),
                Vec3(0.42, 0.42, 0.42),
                color,
                f"pickup-{i}",
                dynamic=True,
            )
            halo = self.mesh(
                Vec3(x, 0.18, z),
                Vec3(0.62, 0.06, 0.62),
                Color(color.r * 0.6, color.g * 0.6, color.b * 0.6, 1),
                f"pickup-halo-{i}",
                dynamic=True,
            )
            self.pickups.append(
                {
                    "x": x,
                    "z": z,
                    "kind": kind,
                    "core": core,
                    "halo": halo,
                    "active": True,
                    "phase": i * 0.8,
                }
            )

    def _build_weapon_and_ui(self) -> None:
        self.weapon = [
            self.mesh(Vec3(), Vec3(0.22, 0.18, 0.62), Color(0.10, 0.30, 0.46, 1), "gun-body", dynamic=True),
            self.mesh(Vec3(), Vec3(0.14, 0.09, 0.40), Color(0.12, 0.62, 0.82, 1), "gun-top", dynamic=True),
            self.mesh(Vec3(), Vec3(0.10, 0.10, 0.42), Color(0.05, 0.09, 0.13, 1), "gun-barrel", dynamic=True),
            self.mesh(Vec3(), Vec3(0.18, 0.18, 0.08), Color(1, 0.72, 0.12, 1), "gun-muzzle", dynamic=True),
        ]
        self.game.directional_light(direction=Vec3(-0.45, -1, -0.35), intensity=0.55)
        self.game.point_light(
            position=Vec3(-7.8, 2.5, 4.2),
            color=Color(0.10, 0.48, 1, 1),
            intensity=9.5,
            range=8.5,
        )
        self.game.point_light(
            position=Vec3(7.8, 2.5, -6.5),
            color=Color(0.85, 0.12, 0.25, 1),
            intensity=8.5,
            range=8,
        )
        self.muzzle_light = self.game.point_light(
            position=Vec3(), color=Color(1, 0.46, 0.08, 1), intensity=0, range=4
        )
        self.hud = self.game.label("", -340, 238, font_size=20)
        self.objective = self.game.label("", 190, 238, font_size=18)
        self.crosshair = self.game.label("+", 0, 0, font_size=30)
        self.help = self.game.label(
            "WASD move   mouse/arrows look   click/SPACE fire   SHIFT sprint   R restart",
            0,
            -252,
            font_size=14,
        )
        self.center = self.game.label("", 0, 175, font_size=24)

    def _sound(self, name: str, volume: float) -> None:
        if not self.audio_enabled:
            return
        try:
            self.game.sound(self.art[name], volume=volume)
        except RuntimeError:
            self.audio_enabled = False

    def _reset(self) -> None:
        self.health, self.ammo, self.kills = 100, 30, 0
        self.won = self.lost = False
        self.shot_cooldown = self.muzzle_flash = self.damage_flash = 0.0
        self.controller.teleport(Vec3(SPAWN.x, SPAWN.y, SPAWN.z))
        self.controller.yaw = self.controller.pitch = 0.0
        for i, enemy in enumerate(self.enemies):
            x, z, _ = ENEMY_SPECS[i]
            enemy["root"].position = Vec3(x, 0.72, z)  # type: ignore[union-attr]
            enemy.update(
                hp=4,
                alive=True,
                cooldown=0.0,
                flash=0.0,
                phase=i * 1.1,
            )
            enemy["collider"].enabled = True  # type: ignore[union-attr]
            enemy["body"].enabled = True  # type: ignore[union-attr]
        for pickup in self.pickups:
            pickup["active"] = True
            pickup["core"].visible = True  # type: ignore[union-attr]
            pickup["halo"].visible = True  # type: ignore[union-attr]
        self.controller.update(CharacterInput3D(), FIXED_DT)

    def _visible(self, enemy: dict[str, object]) -> bool:
        root = enemy["root"]
        start = Vec3(root.position.x, 1.25, root.position.z)  # type: ignore[union-attr]
        delta = self.player.position + Vec3(0, 0.65, 0) - start
        return (
            self.world.sweep_sphere(
                SphereBounds3D(start.x, start.y, start.z, 0.03),
                delta,
                mask=WORLD,
                ignore=enemy["collider"],  # type: ignore[arg-type]
            )
            is None
        )

    def _enemy_ai(self, dt: float) -> None:
        for enemy in self.enemies:
            if not enemy["alive"]:
                continue
            enemy["cooldown"] = max(0.0, float(enemy["cooldown"]) - dt)
            enemy["flash"] = max(0.0, float(enemy["flash"]) - dt)
            enemy["phase"] = float(enemy["phase"]) + dt * 4.5
            root, origin = enemy["root"], enemy["origin"]
            position = root.position  # type: ignore[union-attr]
            distance = dist_xz(position, self.player.position)

            if distance < 13.5 and self._visible(enemy):
                delta = self.player.position - position
                length = max(0.001, math.hypot(delta.x, delta.z))
                if distance > 1.55:
                    move = Vec3(delta.x / length * 1.65 * dt, 0, delta.z / length * 1.65 * dt)
                    hit = self.world.sweep_sphere(
                        SphereBounds3D(position.x, 0.72, position.z, 0.31),
                        move,
                        mask=WORLD,
                        ignore=enemy["collider"],  # type: ignore[arg-type]
                    )
                    if hit is None:
                        root.position = position + move  # type: ignore[union-attr]
                elif float(enemy["cooldown"]) <= 0:
                    self.health = max(0, self.health - 13)
                    enemy["cooldown"] = 0.72
                    self.damage_flash = 0.18
                    self._sound("damage", 0.28)
                    self.lost = self.health <= 0
            else:
                phase = float(enemy["phase"])
                patrol = float(enemy["patrol"])
                target = Vec3(
                    origin.x + math.sin(phase * 0.35) * patrol,  # type: ignore[union-attr]
                    0.72,
                    origin.z + math.cos(phase * 0.35) * patrol,  # type: ignore[union-attr]
                )
                delta = target - position
                length = math.hypot(delta.x, delta.z)
                if length > 0.05:
                    step = min(0.65 * dt, length)
                    move = Vec3(delta.x / length * step, 0, delta.z / length * step)
                    hit = self.world.sweep_sphere(
                        SphereBounds3D(position.x, 0.72, position.z, 0.31),
                        move,
                        mask=WORLD,
                        ignore=enemy["collider"],  # type: ignore[arg-type]
                    )
                    if hit is None:
                        root.position = position + move  # type: ignore[union-attr]

    def _shoot(self) -> None:
        if self.won or self.lost or self.shot_cooldown > 0 or self.ammo <= 0:
            return
        self.ammo -= 1
        self.shot_cooldown, self.muzzle_flash = 0.12, 0.075
        self._sound("shot", 0.24)
        origin = self.camera.position + self.camera.forward * 0.20
        hit = self.world.sweep_sphere(
            SphereBounds3D(origin.x, origin.y, origin.z, 0.025),
            self.camera.forward * 28,
            mask=WORLD | ENEMY,
            ignore=self.player_collider,
        )
        if hit is None or not hit.collider.tag.startswith("enemy:"):
            return
        index = int(hit.collider.tag.split(":", 1)[1])
        enemy = self.enemies[index]
        if not enemy["alive"]:
            return
        enemy["hp"] = int(enemy["hp"]) - 1
        enemy["flash"] = 0.10
        if int(enemy["hp"]) <= 0:
            enemy["alive"] = False
            enemy["collider"].enabled = False  # type: ignore[union-attr]
            enemy["body"].enabled = False  # type: ignore[union-attr]
            self.kills += 1

    def _collect(self) -> None:
        for pickup in self.pickups:
            if not pickup["active"]:
                continue
            point = Vec3(float(pickup["x"]), 0, float(pickup["z"]))
            if dist_xz(self.player.position, point) > 0.85:
                continue
            pickup["active"] = False
            pickup["core"].visible = False  # type: ignore[union-attr]
            pickup["halo"].visible = False  # type: ignore[union-attr]
            self._sound("pickup", 0.22)
            if pickup["kind"] == "ammo":
                self.ammo = min(60, self.ammo + 18)
            else:
                self.health = min(100, self.health + 35)

    def _input(self, dt: float) -> CharacterInput3D:
        move_x = float(self.game.key("D")) - float(self.game.key("A"))
        move_z = float(self.game.key("W")) - float(self.game.key("S"))
        look_yaw = float(self.game.key("RIGHT")) - float(self.game.key("LEFT"))
        look_pitch = float(self.game.key("UP")) - float(self.game.key("DOWN"))
        safe_dt = max(dt, 1 / 500)
        look_yaw += max(-45.0, min(45.0, self.game.input.mouse_dx)) * 0.00115 / safe_dt
        look_pitch -= max(-45.0, min(45.0, self.game.input.mouse_dy)) * 0.00115 / safe_dt
        return CharacterInput3D(
            move_x=move_x,
            move_z=move_z,
            sprint=self.game.key("LEFT_SHIFT") or self.game.key("RIGHT_SHIFT"),
            look_yaw=look_yaw,
            look_pitch=look_pitch,
        )

    def _sync_visuals(self, dt: float) -> None:
        self.phase += dt * (9 + self.controller.state.horizontal_speed)
        for i, enemy in enumerate(self.enemies):
            visual = enemy["visual"]
            for node in visual:  # type: ignore[union-attr]
                node.visible = bool(enemy["alive"])
            if not enemy["alive"]:
                continue
            p = enemy["root"].position  # type: ignore[union-attr]
            bob = math.sin(float(enemy["phase"]) * 1.8 + i) * 0.035
            walk = math.sin(float(enemy["phase"]) * 3 + i) * 0.08
            positions = (
                Vec3(p.x, 0.82 + bob, p.z),
                Vec3(p.x, 1.43 + bob, p.z),
                Vec3(p.x, 1.47 + bob, p.z - 0.285),
                Vec3(p.x - 0.47, 0.89 + bob + walk, p.z),
                Vec3(p.x + 0.47, 0.89 + bob - walk, p.z),
                Vec3(p.x - 0.20, 0.25 + walk, p.z),
                Vec3(p.x + 0.20, 0.25 - walk, p.z),
            )
            for node, position in zip(visual, positions, strict=True):  # type: ignore[arg-type]
                node.position = position
            visual[0].color = (  # type: ignore[index]
                Color(1, 0.52, 0.16, 1)
                if float(enemy["flash"]) > 0
                else Color(0.70, 0.08, 0.16, 1)
            )

        for i, pickup in enumerate(self.pickups):
            if not pickup["active"]:
                continue
            pickup["phase"] = float(pickup["phase"]) + dt * (2 + i * 0.15)
            y = 0.50 + math.sin(float(pickup["phase"])) * 0.10
            core, halo = pickup["core"], pickup["halo"]
            core.position = Vec3(float(pickup["x"]), y, float(pickup["z"]))  # type: ignore[union-attr]
            core.rotation.y += dt * 70  # type: ignore[union-attr]
            halo.rotation.y -= dt * 45  # type: ignore[union-attr]

        forward, right = self.camera.forward, self.camera.right
        base = (
            self.camera.position
            + forward * 0.72
            + right * 0.28
            + Vec3(0, -0.25 - math.sin(self.phase) * 0.018, 0)
        )
        rotation = Vec3(-self.controller.pitch, self.controller.yaw, 0)
        self.weapon[0].position, self.weapon[0].rotation = base, rotation
        self.weapon[1].position = base + Vec3(0, 0.11, 0) + forward * 0.02
        self.weapon[1].rotation = rotation
        self.weapon[2].position = base + forward * 0.39
        self.weapon[2].rotation = rotation
        muzzle = base + forward * 0.64
        self.weapon[3].position = muzzle
        self.weapon[3].rotation = rotation
        self.weapon[3].visible = self.muzzle_flash > 0
        self.muzzle_light.position = muzzle
        self.muzzle_light.intensity = 12 if self.muzzle_flash > 0 else 0

        unlocked = self.kills == len(self.enemies)
        self.exit_core.color = (
            Color(0.08, 0.82, 0.38, 1) if unlocked else Color(0.25, 0.08, 0.10, 1)
        )
        self.hud.text = (
            f"HP {self.health:03d}   AMMO {self.ammo:02d}   "
            f"HOSTILES {len(self.enemies) - self.kills}"
        )
        if self.won:
            self.objective.text = "SECTOR CLEAR"
            self.center.text = "SWIRENGINE 3D — MISSION COMPLETE"
        elif self.lost:
            self.objective.text = "PLAYER DOWN — press R"
            self.center.text = "SYSTEM FAILURE"
        elif unlocked:
            self.objective.text = "Exit unlocked — reach the green door"
            self.center.text = ""
        else:
            self.objective.text = "Clear the bunker"
            self.center.text = "DAMAGE" if self.damage_flash > 0 else ""

    def _update(self, dt: float) -> None:
        self.frames += 1
        dt = max(0.0, min(float(dt), 1 / 20))
        self.shot_cooldown = max(0.0, self.shot_cooldown - dt)
        self.muzzle_flash = max(0.0, self.muzzle_flash - dt)
        self.damage_flash = max(0.0, self.damage_flash - dt)
        if self.game.key_pressed("R"):
            self._reset()
        if not self.won and not self.lost:
            self.controller.update(self._input(dt), dt)
            self._enemy_ai(dt)
            self.world.step(dt)
            self._collect()
            if self.game.input.mouse_button_pressed(0) or self.game.key_pressed("SPACE"):
                self._shoot()
            if self.kills == len(self.enemies) and dist_xz(self.player.position, EXIT) < 1.25:
                self.won = True
            if self.player.position.y < -4:
                self.health, self.lost = 0, True
        self._sync_visuals(dt)
        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES and self.frames < SMOKE_FRAMES:
            raise AssertionError("3D game demo stopped before the requested smoke frame count")
        if SMOKE_FRAMES:
            print(
                "SwirEngine 3D Game Demo smoke OK: "
                f"frames={self.frames}, hp={self.health}, ammo={self.ammo}, kills={self.kills}"
            )


def main() -> None:
    if HEADLESS:
        print(f"SwirEngine 3D Game Demo headless OK: {run_headless_probe()}")
    else:
        FPSDemo().run()


if __name__ == "__main__":
    main()
