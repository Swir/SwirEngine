"""SwirEngine 2D Game Demo — source-only scrolling platformer showcase.

Core movement/collision uses SwirEngine PhysicsWorld2D, RigidBody2D and CollisionWorld2D. Visuals
use layered engine primitives, camera parallax, pooled particles and UI; no third-party game assets.
"""

from __future__ import annotations

import math
import os

from swirengine import (
    AABB,
    BoxCollider2D,
    CollisionWorld2D,
    Color,
    Game,
    PhysicsWorld2D,
    Rectangle2D,
    RigidBody2D,
    Sprite2D,
)

from procedural_art import ensure_art

W, H = 960, 540
FIXED_DT = 1.0 / 120.0
SMOKE_FRAMES = int(os.environ.get("SWIR_GAME_DEMO_SMOKE_FRAMES", "0"))
HEADLESS = os.environ.get("SWIR_GAME_DEMO_HEADLESS") == "1"
SOLID, PLAYER, ENEMY = 1, 2, 4
PW, PH = 30.0, 46.0
RUN_SPEED, JUMP_SPEED = 320.0, 760.0
SPAWN = (-1360.0, -166.0)
CHECKPOINT_X, GOAL_X = 500.0, 1495.0
WORLD_LEFT, WORLD_RIGHT = -1480.0, 1580.0

PLATFORMS = (
    (-1170, -225, 620, 70, 0), (-650, -225, 260, 70, 1), (-300, -225, 300, 70, 2),
    (120, -225, 380, 70, 0), (610, -225, 310, 70, 1), (1060, -225, 410, 70, 2),
    (1450, -225, 230, 70, 0), (-840, -105, 180, 24, 2), (-500, 10, 210, 24, 1),
    (-110, 85, 230, 24, 2), (320, 10, 210, 24, 1), (690, 95, 220, 24, 2),
    (1040, 25, 190, 24, 1), (1290, 110, 180, 24, 2),
)
SHARDS = (
    (-1280.0, -158.0), (-845.0, -60.0), (-500.0, 55.0), (-110.0, 130.0),
    (315.0, 55.0), (690.0, 140.0), (1040.0, 70.0), (1290.0, 155.0),
)
ENEMIES = (
    (-650.0, -169.0, 90.0, 70.0), (-295.0, -169.0, 105.0, 82.0),
    (605.0, -169.0, 105.0, 88.0), (1060.0, -169.0, 120.0, 94.0),
)


def run_headless_probe() -> dict[str, float | int | bool]:
    collisions = CollisionWorld2D(cell_size=96.0)
    physics = PhysicsWorld2D(collisions, gravity=(0.0, -1800.0))
    floor = Rectangle2D(0, -80, 500, 40)
    collisions.add(BoxCollider2D(floor, layer=SOLID, mask=PLAYER, tag="solid"))
    player = Rectangle2D(0, 40, PW, PH, visible=False)
    collider = collisions.add(BoxCollider2D(player, layer=PLAYER, mask=SOLID, tag="player"))
    body = physics.add(RigidBody2D(player, collider))
    for _ in range(180):
        physics.step(FIXED_DT)
    floor_y = -80 + 20 + PH / 2
    if abs(player.y - floor_y) > 0.1:
        raise AssertionError("2D demo player did not settle through PhysicsWorld2D")
    start = player.y
    body.apply_impulse(0, JUMP_SPEED)
    peak = start
    for _ in range(180):
        physics.step(FIXED_DT)
        peak = max(peak, player.y)
    if peak - start < 100 or abs(player.y - floor_y) > 0.2:
        raise AssertionError("2D demo engine-driven jump/landing failed")
    grounded = collisions.overlap_aabb(
        AABB(player.x, player.y - PH / 2 - 2, PW * 0.7, 5), layer_mask=SOLID, tag="solid"
    )
    if not grounded:
        raise AssertionError("2D demo CollisionWorld2D ground query failed")
    return {"jump_height": round(peak - start, 3), "landed": True, "engine_physics": True}


class PlatformerDemo:
    def __init__(self) -> None:
        self.game = Game("SwirEngine 2D Game Demo", W, H, target_fps=144, fixed_hz=120)
        self.game.physics.gravity = (0.0, -1800.0)
        self.art = ensure_art()
        self.audio_enabled = True
        self.frames = 0
        self.phase = 0.0
        self._background()
        self._level()
        self._player()
        self._enemies()
        self._pickups_goal()
        self._vfx_ui()
        self._reset()
        self.game.fixed_update(self._fixed)
        self.game.update(self._update)

    def rect(self, x: float, y: float, w: float, h: float, color: Color, **kw: object) -> Rectangle2D:
        return self.game.add(Rectangle2D(x, y, w, h, color, **kw))

    def _background(self) -> None:
        self.sky = self.rect(0, 0, 1500, 700, Color(0.035, 0.055, 0.14, 1), layer=-100)
        self.moon = self.rect(290, 160, 105, 105, Color(0.72, 0.86, 1, 1), rotation=45, layer=-96)
        self.stars = [
            self.rect(-620 + (i * 157) % 1240, 20 + (i * 73) % 235, 2 + i % 3, 2 + i % 3,
                      Color(0.55, 0.78, 1, 0.75), rotation=45, layer=-95)
            for i in range(38)
        ]
        self.mountains = [
            self.rect(-720 + i * 150, -75, 220, 180 + i % 4 * 30, Color(0.055, 0.105, 0.19, 1),
                      rotation=45, layer=-90)
            for i in range(11)
        ]
        self.city = [
            self.rect(-680 + i * 60, -175, 42, 55 + (i * 29) % 95, Color(0.035, 0.07, 0.12, 1), layer=-80)
            for i in range(24)
        ]

    def _level(self) -> None:
        palette = (
            (Color(0.07, 0.28, 0.40, 1), Color(0.10, 0.80, 0.72, 1)),
            (Color(0.10, 0.32, 0.46, 1), Color(0.24, 0.72, 1, 1)),
            (Color(0.12, 0.27, 0.50, 1), Color(0.58, 0.48, 1, 1)),
        )
        for i, (x, y, w, h, style) in enumerate(PLATFORMS):
            base, accent = palette[style]
            node = self.rect(x, y, w, h, base, name=f"platform-{i}", tags={"platform"}, layer=-2)
            self.game.collider(node, layer=SOLID, mask=PLAYER, tag="solid")
            self.rect(x, y + h / 2 - 5, w - 8, 8, accent, layer=-1)
            for d in range(max(1, int(w // 90))):
                self.rect(x - w / 2 + 42 + d * 86, y - 8, 18, 18, Color(0.02, 0.10, 0.17, 0.9),
                          rotation=45, layer=-1)
        self.flag_pole = self.rect(CHECKPOINT_X, -133, 12, 116, Color(0.15, 0.3, 0.4, 1))
        self.flag = self.rect(CHECKPOINT_X + 28, -90, 56, 30, Color(0.18, 0.45, 0.62, 1))

    def _player(self) -> None:
        self.player = self.rect(
            *SPAWN, PW, PH, Color(0.08, 0.72, 1, 1), visible=False, name="player-root"
        )
        self.player_collider = self.game.collider(
            self.player, width=PW, height=PH, layer=PLAYER, mask=SOLID, tag="player"
        )
        self.body = self.game.rigidbody(self.player, collider=self.player_collider)
        self.player_sprite = self.game.add(
            Sprite2D(
                self.art["player_idle"],
                x=self.player.x,
                y=self.player.y + 8,
                width=54,
                height=68,
                name="player-art",
                layer=12,
            )
        )

    def _enemies(self) -> None:
        self.enemy_data: list[dict[str, object]] = []
        for i, (x, y, patrol, speed) in enumerate(ENEMIES):
            root = self.rect(x, y, 36, 38, Color(), visible=False, name=f"enemy-root-{i}")
            collider = self.game.collider(
                root, width=36, height=38, layer=ENEMY, mask=0, tag="enemy"
            )
            sprite = self.game.add(
                Sprite2D(
                    self.art["enemy_a"],
                    x=x,
                    y=y + 7,
                    width=54,
                    height=54,
                    name=f"enemy-art-{i}",
                    layer=10,
                )
            )
            self.enemy_data.append(
                {
                    "root": root,
                    "collider": collider,
                    "sprite": sprite,
                    "origin": x,
                    "patrol": patrol,
                    "speed": speed,
                    "direction": 1.0,
                    "alive": True,
                    "phase": i * 1.3,
                }
            )

    def _pickups_goal(self) -> None:
        self.shard_active = [True] * len(SHARDS)
        self.shard_nodes = []
        for i, (x, y) in enumerate(SHARDS):
            glow = self.rect(x, y, 42, 42, Color(0.08, 0.58, 1, 0.18), rotation=45, layer=2)
            core = self.game.add(
                Sprite2D(
                    self.art["shard"],
                    x=x,
                    y=y,
                    width=36,
                    height=42,
                    name=f"energy-shard-{i}",
                    layer=4,
                )
            )
            self.shard_nodes.append((glow, core))
        self.goal = self.rect(GOAL_X, -145, 45, 82, Color(0.20, 0.26, 0.32, 1), layer=0)
        self.rect(GOAL_X - 30, -153, 12, 110, Color(0.16, 0.25, 0.32, 1), layer=1)
        self.rect(GOAL_X + 30, -153, 12, 110, Color(0.16, 0.25, 0.32, 1), layer=1)
        self.portal_sprite = self.game.add(
            Sprite2D(
                self.art["portal"],
                x=GOAL_X,
                y=-145,
                width=74,
                height=112,
                tint=Color(0.30, 0.45, 0.50, 0.42),
                name="portal-art",
                layer=3,
            )
        )
        self.beacon = self.rect(
            GOAL_X, -83, 22, 22, Color(0.22, 0.32, 0.40, 1), rotation=45, layer=5
        )

    def _vfx_ui(self) -> None:
        self.dust = self.game.particles(max_particles=48, rate=0, lifetime=(0.18, 0.42), speed=(45, 120),
                                        angle=(25, 155), size=(4, 9), gravity=(0, -180),
                                        color=Color(0.35, 0.75, 0.92, 0.65), emitting=False, seed=7, layer=4)
        self.spark = self.game.particles(max_particles=64, rate=0, lifetime=(0.25, 0.55), speed=(55, 150),
                                         angle=(0, 360), size=(3, 8), gravity=(0, -100),
                                         color=Color(0.30, 0.92, 1, 1), emitting=False, seed=11, layer=12)
        self.hud = self.game.label("", -360, 238, font_size=20)
        self.objective = self.game.label("", 120, 238, font_size=18)
        self.help = self.game.label("A/D or arrows: move   SPACE: jump   R: restart", 0, -252, font_size=15)
        self.banner = self.game.label("", 0, 190, font_size=26)

    def _sound(self, name: str, volume: float = 0.34) -> None:
        if not self.audio_enabled:
            return
        try:
            self.game.sound(self.art[name], volume=volume)
        except RuntimeError:
            # Audio is an optional SwirEngine extra; the visual demo stays fully playable without it.
            self.audio_enabled = False

    def _reset(self) -> None:
        self.health, self.shards = 3, 0
        self.checkpoint, self.checkpoint_active = SPAWN, False
        self.won = self.lost = False
        self.invulnerable = 0.0
        self.player.x, self.player.y = SPAWN
        self.body.set_velocity(0, 0)
        self.shard_active[:] = [True] * len(SHARDS)
        for i, enemy in enumerate(self.enemy_data):
            x, y, *_ = ENEMIES[i]
            enemy["root"].x, enemy["root"].y = x, y  # type: ignore[union-attr]
            enemy["direction"], enemy["alive"] = 1.0, True
            enemy["collider"].enabled = True  # type: ignore[union-attr]
            enemy["sprite"].visible = True  # type: ignore[union-attr]
        self.player_sprite.tint = Color(1, 1, 1, 1)
        self.dust.clear()
        self.spark.clear()

    def _grounded(self) -> bool:
        sensor = AABB(self.player.x, self.player.y - PH / 2 - 2, PW * 0.68, 6)
        return bool(self.game.collisions.overlap_aabb(sensor, layer_mask=SOLID, tag="solid")) and self.body.velocity_y <= 10

    def _damage(self) -> None:
        if self.invulnerable > 0 or self.won or self.lost:
            return
        self.health -= 1
        self._sound("hit", 0.28)
        if self.health <= 0:
            self.lost = True
            self.body.set_velocity(0, 0)
            return
        self.player.x, self.player.y = self.checkpoint
        self.body.set_velocity(0, 0)
        self.invulnerable = 1.2
        self.dust.x, self.dust.y = self.player.x, self.player.y - PH / 2
        self.dust.burst(12)

    def _fixed(self, _dt: float) -> None:
        if self.won or self.lost:
            return
        move = float(self.game.key("D") or self.game.key("RIGHT")) - float(self.game.key("A") or self.game.key("LEFT"))
        self.body.velocity_x = move * RUN_SPEED

    def _gameplay(self, dt: float) -> None:
        for enemy in self.enemy_data:
            if not enemy["alive"]:
                continue
            enemy["phase"] = float(enemy["phase"]) + dt * 5
            root = enemy["root"]
            direction = float(enemy["direction"])
            root.x += direction * float(enemy["speed"]) * dt  # type: ignore[union-attr]
            origin, patrol = float(enemy["origin"]), float(enemy["patrol"])
            if root.x > origin + patrol or root.x < origin - patrol:  # type: ignore[union-attr]
                enemy["direction"] = -direction
        hits = self.game.collisions.overlap_aabb(AABB(self.player.x, self.player.y, PW, PH), layer_mask=ENEMY, tag="enemy")
        for hit in hits:
            enemy = next((e for e in self.enemy_data if e["collider"] is hit and e["alive"]), None)
            if enemy is None:
                continue
            root = enemy["root"]
            if self.body.velocity_y < -80 and self.player.y > root.y + 14:  # type: ignore[union-attr]
                enemy["alive"] = False
                hit.enabled = False
                self.body.velocity_y = 470
                self.spark.x, self.spark.y = root.x, root.y  # type: ignore[union-attr]
                self.spark.burst(18)
                self._sound("hit", 0.22)
            else:
                self._damage()
            break
        for i, (x, y) in enumerate(SHARDS):
            if self.shard_active[i] and abs(self.player.x - x) <= 28 and abs(self.player.y - y) <= 38:
                self.shard_active[i] = False
                self.shards += 1
                self.spark.x, self.spark.y = x, y
                self.spark.burst(14)
                self._sound("pickup", 0.25)
        if not self.checkpoint_active and self.player.x >= CHECKPOINT_X:
            self.checkpoint_active = True
            self.checkpoint = (CHECKPOINT_X, SPAWN[1])
            self.spark.x, self.spark.y = CHECKPOINT_X, -90
            self.spark.burst(22)
            self._sound("pickup", 0.20)
        if self.player.y < -360:
            self._damage()
        if self.shards == len(SHARDS) and abs(self.player.x - GOAL_X) < 38:
            self.won = True
            self.body.set_velocity(0, 0)
            self.spark.x, self.spark.y = GOAL_X, -125
            self.spark.burst(36)
            self._sound("pickup", 0.32)

    def _sync(self, dt: float) -> None:
        moving = abs(self.body.velocity_x) > 5 and self._grounded()
        self.phase += dt * (12 if moving else 4)
        bob = math.sin(self.phase) * (2 if moving else 0.7)
        facing = -1 if self.body.velocity_x < -1 else 1
        px, py = self.player.x, self.player.y

        self.player_sprite.x = px
        self.player_sprite.y = py + 8 + bob
        if moving:
            self.player_sprite.texture = (
                self.art["player_run_a"] if int(self.phase * 1.35) % 2 == 0
                else self.art["player_run_b"]
            )
        else:
            self.player_sprite.texture = self.art["player_idle"]
        self.player_sprite.uv_rect = (1.0, 0.0, 0.0, 1.0) if facing < 0 else (0.0, 0.0, 1.0, 1.0)
        hurt_flash = self.invulnerable > 0 and int(self.invulnerable * 10) % 2 == 0
        self.player_sprite.tint = Color(1.0, 0.55, 0.45, 1.0) if hurt_flash else Color(1, 1, 1, 1)

        for i, enemy in enumerate(self.enemy_data):
            root = enemy["root"]
            sprite = enemy["sprite"]
            alive, phase = bool(enemy["alive"]), float(enemy["phase"])
            sprite.visible = alive  # type: ignore[union-attr]
            if alive:
                bounce = math.sin(phase + i) * 2.0
                sprite.x = root.x  # type: ignore[union-attr]
                sprite.y = root.y + 7 + bounce  # type: ignore[union-attr]
                sprite.texture = (  # type: ignore[union-attr]
                    self.art["enemy_a"] if int(phase * 1.2) % 2 == 0 else self.art["enemy_b"]
                )
                sprite.uv_rect = (  # type: ignore[union-attr]
                    (1.0, 0.0, 0.0, 1.0)
                    if float(enemy["direction"]) < 0
                    else (0.0, 0.0, 1.0, 1.0)
                )

        pulse = 34 + (0.85 + math.sin(self.phase * 0.55) * 0.15) * 8
        for i, ((glow, core), active) in enumerate(
            zip(self.shard_nodes, self.shard_active, strict=True)
        ):
            glow.visible = core.visible = active
            glow.width = glow.height = pulse
            glow.rotation -= dt * 24
            core.rotation += dt * (35 + i * 2)
            core.y = SHARDS[i][1] + math.sin(self.phase * 0.45 + i) * 5

        unlocked = self.shards == len(SHARDS)
        self.goal.color = (
            Color(0.16, 1, 0.55, 0.16) if unlocked else Color(0.20, 0.26, 0.32, 1)
        )
        self.portal_sprite.tint = (
            Color(0.72, 1.0, 0.90, 1.0) if unlocked else Color(0.26, 0.38, 0.42, 0.42)
        )
        self.portal_sprite.rotation = math.sin(self.phase * 0.18) * 1.5
        self.beacon.color = (
            Color(0.20, 1, 0.72, 1) if unlocked else Color(0.22, 0.32, 0.40, 1)
        )
        self.beacon.rotation += dt * 45
        self.flag.color = (
            Color(0.18, 1, 0.68, 1)
            if self.checkpoint_active
            else Color(0.18, 0.45, 0.62, 1)
        )

        camera = self.game.camera
        target = max(WORLD_LEFT + W / 2, min(WORLD_RIGHT - W / 2, px))
        camera.x += (target - camera.x) * min(1, dt * 5)
        camera.y += ((py + 20) * 0.18 - camera.y) * min(1, dt * 3)
        self.sky.x, self.sky.y = camera.x, camera.y
        self.moon.x = camera.x * 0.12 + 290
        for i, star in enumerate(self.stars):
            star.x = camera.x * 0.08 - 620 + (i * 157) % 1240
        for i, node in enumerate(self.mountains):
            node.x = camera.x * 0.35 - 720 + i * 150
        for i, node in enumerate(self.city):
            node.x = camera.x * 0.62 - 680 + i * 60

        self.hud.text = f"HP {self.health}    ENERGY {self.shards}/{len(SHARDS)}"
        if self.won:
            self.objective.text, self.banner.text = (
                "LEVEL COMPLETE",
                "SWIRENGINE 2D — SECTOR CLEARED",
            )
        elif self.lost:
            self.objective.text, self.banner.text = "GAME OVER — press R", "SYSTEM OFFLINE"
        elif unlocked:
            self.objective.text, self.banner.text = "Portal online — reach the green gate", ""
        elif self.checkpoint_active:
            self.objective.text, self.banner.text = (
                "Checkpoint active — recover all energy shards",
                "",
            )
        else:
            self.objective.text, self.banner.text = (
                "Recover every energy shard and reach the portal",
                "",
            )

    def _update(self, dt: float) -> None:
        self.frames += 1
        self.invulnerable = max(0.0, self.invulnerable - dt)
        if self.game.key_pressed("R"):
            self._reset()
        if not self.won and not self.lost:
            if self.game.key_pressed("SPACE") and self._grounded():
                self.body.velocity_y = JUMP_SPEED
                self.dust.x, self.dust.y = self.player.x, self.player.y - PH / 2
                self.dust.burst(8)
                self._sound("jump", 0.24)
            self._gameplay(dt)
        self._sync(dt)
        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES and self.frames < SMOKE_FRAMES:
            raise AssertionError("2D game demo stopped before the requested smoke frame count")
        if SMOKE_FRAMES:
            print(f"SwirEngine 2D Game Demo smoke OK: frames={self.frames}, hp={self.health}, shards={self.shards}")


def main() -> None:
    if HEADLESS:
        print(f"SwirEngine 2D Game Demo headless OK: {run_headless_probe()}")
    else:
        PlatformerDemo().run()


if __name__ == "__main__":
    main()
