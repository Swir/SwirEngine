"""Shadow Relic 32 — a SwirEngine 2.2.x 32-bit-era adventure platformer.

The rendered game uses SwirEngine's real 2D runtime: PhysicsWorld2D/RigidBody2D,
CollisionWorld2D, Sprite2D, camera, particles, audio and SaveStore. Artwork/audio are
original and generated from source by procedural_art.py on first launch.
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Any

from procedural_art import asset_root, ensure_art
from swirengine import (
    AABB,
    BoxCollider2D,
    CollisionWorld2D,
    Color,
    Game,
    PhysicsWorld2D,
    Rectangle2D,
    RigidBody2D,
    SaveStore,
)

W, H = 1280, 720
FIXED_DT = 1.0 / 120.0
SMOKE_FRAMES = int(os.environ.get("SHADOW_RELIC_SMOKE_FRAMES", "0"))
HEADLESS = os.environ.get("SHADOW_RELIC_HEADLESS") == "1"

SOLID, PLAYER, ENEMY = 1, 2, 4
PLAYER_W, PLAYER_H = 34.0, 54.0
RUN_SPEED = 330.0
JUMP_SPEED = 755.0
GRAVITY = -1880.0
WORLD_LEFT, WORLD_RIGHT = -1650.0, 5150.0
SPAWN = (-1480.0, -160.0)
GATE_X = 2680.0
BOSS_ARENA_LEFT, BOSS_ARENA_RIGHT = 3650.0, 4720.0
EXIT_X = 4920.0

PLATFORMS = (
    (-1350, -250, 650, 90, "ruins"), (-650, -250, 560, 90, "ruins"),
    (0, -250, 590, 90, "cave"), (690, -250, 590, 90, "cave"),
    (1370, -250, 590, 90, "cave"), (2040, -250, 560, 90, "cave"),
    (2650, -250, 520, 90, "temple"), (3290, -250, 600, 90, "temple"),
    (3970, -250, 600, 90, "temple"), (4730, -250, 850, 90, "temple"),
    (-1040, -95, 220, 24, "ruins"), (-620, 20, 200, 24, "ruins"),
    (-180, 105, 210, 24, "cave"), (350, 20, 240, 24, "cave"),
    (880, 115, 220, 24, "cave"), (1420, 35, 220, 24, "cave"),
    (1900, 125, 210, 24, "cave"), (2340, 35, 190, 24, "cave"),
    (2940, 115, 240, 24, "temple"), (3380, 20, 200, 24, "temple"),
    (3820, 125, 230, 24, "temple"), (4300, 35, 200, 24, "temple"),
    (4700, 120, 220, 24, "temple"),
)

SIGILS = (
    ("sun", -620.0, 82.0),
    ("moon", 1420.0, 96.0),
    ("void", 2340.0, 96.0),
)

SHARDS = (
    (-1430, -155), (-1050, -45), (-620, 70), (-180, 155), (340, 70),
    (880, 165), (1430, 85), (1900, 175), (2335, 85), (2940, 165),
    (3820, 175), (4700, 170),
)

POTIONS = ((520.0, -155.0), (3300.0, -155.0))
CHECKPOINTS = ((450.0, -155.0), (3070.0, -155.0))

ENEMY_SPECS = (
    ("crawler", -850.0, -158.0, 115.0, 74.0, 1),
    ("crawler", -90.0, -158.0, 120.0, 82.0, 1),
    ("wisp", 640.0, -20.0, 130.0, 62.0, 1),
    ("cultist", 1180.0, -151.0, 120.0, 68.0, 2),
    ("crawler", 1780.0, -158.0, 125.0, 88.0, 1),
    ("wisp", 2170.0, 40.0, 120.0, 70.0, 1),
    ("cultist", 3180.0, -151.0, 145.0, 74.0, 2),
    ("crawler", 3550.0, -158.0, 100.0, 94.0, 1),
)

DIALOG = (
    "ARCHIVIST: The Moon Temple is sealed by three lost sigils.",
    "Find Sun, Moon and Void. The old gate will answer to all three.",
    "Beyond it waits the Shadow Warden. X or J swings your relic blade.",
)


def run_headless_probe() -> dict[str, object]:
    collisions = CollisionWorld2D(cell_size=96.0)
    physics = PhysicsWorld2D(collisions, gravity=(0.0, GRAVITY))
    floor = Rectangle2D(0, -80, 500, 40)
    collisions.add(BoxCollider2D(floor, layer=SOLID, mask=PLAYER, tag="solid"))
    player = Rectangle2D(0, 40, PLAYER_W, PLAYER_H, visible=False)
    collider = collisions.add(BoxCollider2D(player, layer=PLAYER, mask=SOLID, tag="player"))
    body = physics.add(RigidBody2D(player, collider))
    for _ in range(180):
        physics.step(FIXED_DT)
    floor_y = -80 + 20 + PLAYER_H / 2
    if abs(player.y - floor_y) > 0.15:
        raise AssertionError("Shadow Relic player did not settle on SwirEngine collision geometry")
    body.apply_impulse(0, JUMP_SPEED)
    peak = player.y
    for _ in range(180):
        physics.step(FIXED_DT)
        peak = max(peak, player.y)
    if peak - floor_y < 100 or abs(player.y - floor_y) > 0.25:
        raise AssertionError("Shadow Relic jump/landing probe failed")
    with tempfile.TemporaryDirectory() as tmp:
        save = SaveStore(Path(tmp) / "save.json", defaults={"checkpoint": 0, "sigils": []})
        save.update({"checkpoint": 1, "sigils": ["sun"]}).save()
        loaded = SaveStore(save.path, defaults={"checkpoint": 0, "sigils": []})
        if loaded.get("checkpoint") != 1 or loaded.get("sigils") != ["sun"]:
            raise AssertionError("Shadow Relic SaveStore persistence probe failed")
    return {
        "engine_physics": True,
        "landed": True,
        "jump_height": round(peak - floor_y, 2),
        "save_store": True,
    }


class ShadowRelic32:
    def __init__(self) -> None:
        self.art = ensure_art()
        self.assets = asset_root()
        self.game = Game(
            "Shadow Relic 32 — The Moon Temple",
            W,
            H,
            mode="2d",
            target_fps=144,
            fixed_hz=120,
            asset_root=self.assets,
        )
        self.game.physics.gravity = (0.0, GRAVITY)
        self.frames = 0
        self.time = 0.0
        self.phase = 0.0
        self.audio_ok = True
        self.health = 5
        self.shards = 0
        self.attack_timer = 0.0
        self.attack_cooldown = 0.0
        self.invulnerable = 0.0
        self.dialog_index = -1
        self.dialog_timer = 0.0
        self.won = False
        self.game_over = False
        self.checkpoint_index = 0
        self.collected_sigils: set[str] = set()
        self.boss_defeated = False

        save_path = Path.home() / ".shadow_relic_32" / "save.json"
        self.save = SaveStore(
            save_path,
            defaults={
                "checkpoint": 0,
                "sigils": [],
                "boss_defeated": False,
                "best_shards": 0,
            },
        )
        self._load_progress()
        self._background()
        self._level()
        self._player()
        self._npc()
        self._enemies()
        self._collectibles()
        self._boss()
        self._portal()
        self._vfx_ui()
        self._reset_player(full=False)
        self.game.fixed_update(self._fixed)
        self.game.update(self._update)

    def rect(self, x: float, y: float, w: float, h: float, color: Color, **kwargs: Any) -> Rectangle2D:
        return self.game.add(Rectangle2D(x, y, w, h, color, **kwargs))

    def _load_progress(self) -> None:
        self.checkpoint_index = max(0, min(2, int(self.save.get("checkpoint", 0))))
        self.collected_sigils = {str(value) for value in self.save.get("sigils", [])}
        self.boss_defeated = bool(self.save.get("boss_defeated", False))
        self.shards = 0

    def _save_progress(self) -> None:
        self.save.update(
            {
                "checkpoint": self.checkpoint_index,
                "sigils": sorted(self.collected_sigils),
                "boss_defeated": self.boss_defeated,
                "best_shards": max(int(self.save.get("best_shards", 0)), self.shards),
            }
        ).save()

    def _background(self) -> None:
        self.sky = self.rect(0, 0, 1600, 900, Color(0.02, 0.025, 0.07, 1), layer=-300)
        self.bg_far = [self.game.sprite("bg_far.png", x=i * 1280, y=0, width=1280, height=720, layer=-290) for i in range(6)]
        self.bg_mid = [self.game.sprite("bg_mid.png", x=i * 1280, y=0, width=1280, height=720, layer=-280) for i in range(6)]
        self.bg_front = [self.game.sprite("bg_front.png", x=i * 1280, y=0, width=1280, height=720, layer=-270) for i in range(6)]

    def _level(self) -> None:
        self.platforms: list[Rectangle2D] = []
        self.platform_colliders: list[BoxCollider2D] = []
        for i, (x, y, w, h, style) in enumerate(PLATFORMS):
            node = self.rect(x, y, w, h, Color(0.12, 0.13, 0.18, 1), visible=False, name=f"solid-{i}")
            collider = self.game.collider(node, layer=SOLID, mask=PLAYER, tag="solid")
            self.platforms.append(node)
            self.platform_colliders.append(collider)
            tile_count = max(1, int(math.ceil(w / 128)))
            for tile in range(tile_count):
                tx = x - w / 2 + min(w - 64, 64 + tile * 128)
                self.game.sprite(f"platform_{style}.png", x=tx, y=y, width=min(128, w), height=max(64, h), layer=-2)
        self.gate = self.rect(GATE_X, -105, 54, 200, Color(0.20, 0.10, 0.28, 0.95), layer=7)
        self.gate_collider = self.game.collider(self.gate, layer=SOLID, mask=PLAYER, tag="solid")
        self.gate_rune = self.rect(GATE_X, -70, 28, 28, Color(0.65, 0.28, 0.85, 1), rotation=45, layer=8)

    def _player(self) -> None:
        self.player = self.rect(*SPAWN, PLAYER_W, PLAYER_H, Color(), visible=False, name="player-root")
        self.player_collider = self.game.collider(self.player, layer=PLAYER, mask=SOLID, tag="player")
        self.body = self.game.rigidbody(self.player, collider=self.player_collider)
        self.hero = self.game.sprite("hero_idle0_r.png", x=self.player.x, y=self.player.y + 8, width=92, height=92, layer=20)
        self.hero_shadow = self.rect(self.player.x, self.player.y - 31, 58, 12, Color(0, 0, 0, 0.34), layer=10)
        self.facing = 1

    def _npc(self) -> None:
        self.archivist_x = -1330.0
        self.archivist = self.game.sprite("archivist.png", x=self.archivist_x, y=-145, width=88, height=88, layer=15)
        self.archivist_glow = self.rect(self.archivist_x, -145, 66, 66, Color(0.18, 0.70, 0.72, 0.10), rotation=45, layer=13)

    def _make_enemy(self, kind: str, x: float, y: float, patrol: float, speed: float, hp: int) -> dict[str, Any]:
        size = 82 if kind != "wisp" else 72
        root = self.rect(x, y, 40, 44, Color(), visible=False, name=f"enemy-{kind}-{len(self.enemies)}")
        collider = self.game.collider(root, width=40, height=44, layer=ENEMY, mask=0, tag="enemy")
        sprite_name = "crawler0_r.png" if kind == "crawler" else ("wisp0.png" if kind == "wisp" else "cultist0_r.png")
        sprite = self.game.sprite(sprite_name, x=x, y=y + 9, width=size, height=size, layer=16)
        return {
            "kind": kind,
            "root": root,
            "collider": collider,
            "sprite": sprite,
            "origin": x,
            "base_y": y,
            "patrol": patrol,
            "speed": speed,
            "direction": 1.0,
            "hp": hp,
            "alive": True,
            "phase": 0.0,
            "flash": 0.0,
        }

    def _enemies(self) -> None:
        self.enemies: list[dict[str, Any]] = []
        for spec in ENEMY_SPECS:
            self.enemies.append(self._make_enemy(*spec))

    def _collectibles(self) -> None:
        self.sigil_nodes: dict[str, tuple[Rectangle2D, Any]] = {}
        for name, x, y in SIGILS:
            glow = self.rect(x, y, 74, 74, Color(0.35, 0.75, 1.0, 0.12), rotation=45, layer=5)
            sprite = self.game.sprite(f"sigil_{name}.png", x=x, y=y, width=76, height=76, layer=7)
            active = name not in self.collected_sigils
            glow.visible = sprite.visible = active
            self.sigil_nodes[name] = (glow, sprite)
        self.shard_active = [True] * len(SHARDS)
        self.shard_nodes: list[tuple[Rectangle2D, Any]] = []
        for x, y in SHARDS:
            glow = self.rect(x, y, 46, 46, Color(0.2, 0.95, 1.0, 0.10), rotation=45, layer=5)
            sprite = self.game.sprite("shard.png", x=x, y=y, width=42, height=42, layer=7)
            self.shard_nodes.append((glow, sprite))
        self.potion_active = [True] * len(POTIONS)
        self.potion_nodes = [self.game.sprite("potion.png", x=x, y=y, width=48, height=48, layer=7) for x, y in POTIONS]
        self.checkpoint_nodes = [self.game.sprite("checkpoint.png", x=x, y=y + 26, width=64, height=64, layer=8) for x, y in CHECKPOINTS]

    def _boss(self) -> None:
        self.boss = self._make_enemy("boss", 4260.0, -128.0, 300.0, 82.0, 7)
        self.boss["sprite"].texture = str(self.assets / "warden0_r.png")
        self.boss["sprite"].width = 166
        self.boss["sprite"].height = 166
        self.boss["root"].width = 76
        self.boss["root"].height = 100
        self.boss["collider"].width = 76
        self.boss["collider"].height = 100
        if self.boss_defeated:
            self.boss["alive"] = False
            self.boss["collider"].enabled = False
            self.boss["sprite"].visible = False

    def _portal(self) -> None:
        self.portal = self.game.sprite("portal.png", x=EXIT_X, y=-135, width=116, height=160, layer=9)
        self.portal_glow = self.rect(EXIT_X, -135, 96, 150, Color(0.15, 0.85, 0.72, 0.08), layer=6)

    def _vfx_ui(self) -> None:
        self.dust = self.game.particles(max_particles=50, rate=0, lifetime=(0.16, 0.42), speed=(40, 120), angle=(25, 155), size=(4, 9), gravity=(0, -220), color=Color(0.42, 0.77, 0.78, 0.72), emitting=False, seed=31, layer=12)
        self.spark = self.game.particles(max_particles=80, rate=0, lifetime=(0.22, 0.55), speed=(60, 170), angle=(0, 360), size=(3, 8), gravity=(0, -80), color=Color(0.48, 0.94, 1.0, 1.0), emitting=False, seed=47, layer=24)
        self.hud_panel = self.rect(-420, 309, 420, 60, Color(0.01, 0.015, 0.04, 0.82), screen_space=True, layer=90)
        self.objective_panel = self.rect(310, 309, 555, 60, Color(0.01, 0.015, 0.04, 0.78), screen_space=True, layer=90)
        self.hud = self.game.label("", -515, 309, font_size=19)
        self.objective = self.game.label("", 115, 309, font_size=16)
        self.zone_label = self.game.label("", 0, 260, font_size=22)
        self.help = self.game.label("A/D move   SPACE jump   X/J sword   E talk   R respawn   N new game", 0, -330, font_size=14)
        self.dialog = self.game.label("", 0, -270, font_size=18)
        self.banner = self.game.label("", 0, 205, font_size=30)
        self.boss_label = self.game.label("", 0, 170, font_size=18)
        self.scanlines = [self.rect(0, -330 + i * 14, 1280, 1, Color(0, 0, 0, 0.11), screen_space=True, layer=120) for i in range(48)]

    def _checkpoint_position(self) -> tuple[float, float]:
        if self.checkpoint_index <= 0:
            return SPAWN
        return CHECKPOINTS[self.checkpoint_index - 1]

    def _reset_player(self, *, full: bool = False) -> None:
        if full:
            self.health = 5
            self.collected_sigils.clear()
            self.boss_defeated = False
            self.checkpoint_index = 0
            self.shards = 0
            self.save.clear().save()
            for name, _x, _y in SIGILS:
                glow, sprite = self.sigil_nodes[name]
                glow.visible = sprite.visible = True
            self.boss["alive"] = True
            self.boss["hp"] = 7
            self.boss["collider"].enabled = True
            self.boss["sprite"].visible = True
        self.health = max(1, self.health)
        self.player.x, self.player.y = self._checkpoint_position()
        self.body.set_velocity(0, 0)
        self.invulnerable = 1.0
        self.game_over = False

    def _grounded(self) -> bool:
        sensor = AABB(self.player.x, self.player.y - PLAYER_H / 2 - 2, PLAYER_W * 0.70, 6)
        return bool(self.game.collisions.overlap_aabb(sensor, layer_mask=SOLID, tag="solid")) and self.body.velocity_y <= 12

    def _sound(self, name: str, volume: float = 0.25) -> None:
        if not self.audio_ok:
            return
        try:
            self.game.sound(name, volume=volume)
        except RuntimeError:
            self.audio_ok = False

    def _damage(self) -> None:
        if self.invulnerable > 0 or self.won or self.game_over:
            return
        self.health -= 1
        self._sound("hit.wav", 0.24)
        self.spark.x, self.spark.y = self.player.x, self.player.y
        self.spark.burst(14)
        if self.health <= 0:
            self.game_over = True
            self.body.set_velocity(0, 0)
            return
        self.player.x, self.player.y = self._checkpoint_position()
        self.body.set_velocity(0, 0)
        self.invulnerable = 1.4

    def _attack(self) -> None:
        if self.attack_cooldown > 0 or self.won or self.game_over:
            return
        self.attack_timer = 0.16
        self.attack_cooldown = 0.30
        self._sound("slash.wav", 0.18)
        cx = self.player.x + self.facing * 54
        hits = self.game.collisions.overlap_aabb(AABB(cx, self.player.y, 90, 62), layer_mask=ENEMY, tag="enemy")
        for hit in hits:
            enemy = next((item for item in [*self.enemies, self.boss] if item["collider"] is hit and item["alive"]), None)
            if enemy is None:
                continue
            enemy["hp"] = int(enemy["hp"]) - 1
            enemy["flash"] = 0.12
            self.spark.x, self.spark.y = enemy["root"].x, enemy["root"].y
            self.spark.burst(12 if enemy is not self.boss else 22)
            self._sound("boss_hit.wav" if enemy is self.boss else "hit.wav", 0.20)
            if enemy["hp"] <= 0:
                enemy["alive"] = False
                enemy["collider"].enabled = False
                enemy["sprite"].visible = False
                if enemy is self.boss:
                    self.boss_defeated = True
                    self._save_progress()
                    self.spark.burst(42)
            break

    def _fixed(self, _dt: float) -> None:
        if self.won or self.game_over:
            return
        move = float(self.game.key("D") or self.game.key("RIGHT")) - float(self.game.key("A") or self.game.key("LEFT"))
        self.body.velocity_x = move * RUN_SPEED
        if move < 0:
            self.facing = -1
        elif move > 0:
            self.facing = 1

    def _update_enemies(self, dt: float) -> None:
        for i, enemy in enumerate(self.enemies):
            if not enemy["alive"]:
                continue
            enemy["phase"] = float(enemy["phase"]) + dt * 5.0
            enemy["flash"] = max(0.0, float(enemy["flash"]) - dt)
            root = enemy["root"]
            direction = float(enemy["direction"])
            kind = str(enemy["kind"])
            root.x += direction * float(enemy["speed"]) * dt
            if root.x > float(enemy["origin"]) + float(enemy["patrol"]) or root.x < float(enemy["origin"]) - float(enemy["patrol"]):
                enemy["direction"] = -direction
            if kind == "wisp":
                root.y = float(enemy["base_y"]) + math.sin(float(enemy["phase"])) * 26
            sprite = enemy["sprite"]
            sprite.x = root.x
            sprite.y = root.y + 8
            frame = int(float(enemy["phase"]) * 1.35) % 2
            if kind == "crawler":
                sprite.texture = str(self.assets / f"crawler{frame}_{'r' if float(enemy['direction']) > 0 else 'l'}.png")
            elif kind == "wisp":
                sprite.texture = str(self.assets / f"wisp{frame}.png")
            else:
                sprite.texture = str(self.assets / f"cultist{frame}_{'r' if float(enemy['direction']) > 0 else 'l'}.png")
            sprite.tint = Color(1.0, 0.42, 0.42, 1.0) if float(enemy["flash"]) > 0 else Color(1, 1, 1, 1)

        if self.boss["alive"] and self.player.x > BOSS_ARENA_LEFT - 160:
            boss = self.boss
            root = boss["root"]
            boss["phase"] = float(boss["phase"]) + dt * 3.8
            boss["flash"] = max(0.0, float(boss["flash"]) - dt)
            dx = self.player.x - root.x
            boss["direction"] = 1.0 if dx > 0 else -1.0
            root.x += max(-1.0, min(1.0, dx / 120.0)) * float(boss["speed"]) * dt
            root.x = max(BOSS_ARENA_LEFT, min(BOSS_ARENA_RIGHT, root.x))
            root.y = -128 + abs(math.sin(float(boss["phase"]) * 0.7)) * 7
            sprite = boss["sprite"]
            sprite.x, sprite.y = root.x, root.y + 18
            frame = int(float(boss["phase"]) * 1.1) % 3
            sprite.texture = str(self.assets / f"warden{frame}_{'r' if float(boss['direction']) > 0 else 'l'}.png")
            sprite.tint = Color(1.0, 0.32, 0.35, 1) if float(boss["flash"]) > 0 else Color(1, 1, 1, 1)

    def _contact_damage(self) -> None:
        hits = self.game.collisions.overlap_aabb(AABB(self.player.x, self.player.y, PLAYER_W, PLAYER_H), layer_mask=ENEMY, tag="enemy")
        for hit in hits:
            enemy = next((item for item in [*self.enemies, self.boss] if item["collider"] is hit and item["alive"]), None)
            if enemy is None:
                continue
            if self.body.velocity_y < -100 and self.player.y > enemy["root"].y + 24:
                enemy["hp"] = int(enemy["hp"]) - 1
                self.body.velocity_y = 470
                if enemy["hp"] <= 0:
                    enemy["alive"] = False
                    enemy["collider"].enabled = False
                    enemy["sprite"].visible = False
                    if enemy is self.boss:
                        self.boss_defeated = True
                        self._save_progress()
                return
            self._damage()
            return

    def _collect(self) -> None:
        for name, x, y in SIGILS:
            if name in self.collected_sigils:
                continue
            if abs(self.player.x - x) < 34 and abs(self.player.y - y) < 44:
                self.collected_sigils.add(name)
                glow, sprite = self.sigil_nodes[name]
                glow.visible = sprite.visible = False
                self.spark.x, self.spark.y = x, y
                self.spark.burst(24)
                self._sound("pickup.wav", 0.24)
                self._save_progress()
        for i, (x, y) in enumerate(SHARDS):
            if self.shard_active[i] and abs(self.player.x - x) < 28 and abs(self.player.y - y) < 38:
                self.shard_active[i] = False
                self.shards += 1
                glow, sprite = self.shard_nodes[i]
                glow.visible = sprite.visible = False
                self.spark.x, self.spark.y = x, y
                self.spark.burst(10)
                self._sound("pickup.wav", 0.14)
        for i, (x, y) in enumerate(POTIONS):
            if self.potion_active[i] and abs(self.player.x - x) < 32 and abs(self.player.y - y) < 38:
                self.potion_active[i] = False
                self.potion_nodes[i].visible = False
                self.health = min(5, self.health + 2)
                self._sound("checkpoint.wav", 0.12)
        for index, (x, y) in enumerate(CHECKPOINTS, start=1):
            if index > self.checkpoint_index and self.player.x >= x:
                self.checkpoint_index = index
                self._save_progress()
                self.spark.x, self.spark.y = x, y + 24
                self.spark.burst(24)
                self._sound("checkpoint.wav", 0.24)
        self.gate_collider.enabled = len(self.collected_sigils) < 3
        self.gate.visible = len(self.collected_sigils) < 3
        self.gate_rune.visible = len(self.collected_sigils) < 3
        if self.boss_defeated and abs(self.player.x - EXIT_X) < 54:
            self.won = True
            self.body.set_velocity(0, 0)
            self._sound("win.wav", 0.30)
            self.spark.x, self.spark.y = EXIT_X, -120
            self.spark.burst(46)

    def _dialog_update(self, dt: float) -> None:
        near = abs(self.player.x - self.archivist_x) < 105
        if near and self.game.key_pressed("E"):
            self.dialog_index = (self.dialog_index + 1) % len(DIALOG)
            self.dialog_timer = 6.0
        self.dialog_timer = max(0.0, self.dialog_timer - dt)
        if near and self.dialog_timer <= 0:
            self.dialog.text = "E — talk to the Archivist"
        elif self.dialog_timer > 0 and self.dialog_index >= 0:
            self.dialog.text = DIALOG[self.dialog_index]
        else:
            self.dialog.text = ""

    def _sync_visuals(self, dt: float) -> None:
        self.phase += dt * (10 if abs(self.body.velocity_x) > 5 else 3.5)
        side = "r" if self.facing > 0 else "l"
        if self.attack_timer > 0:
            texture = f"hero_attack_{side}.png"
        elif self.invulnerable > 0 and int(self.invulnerable * 10) % 2 == 0:
            texture = f"hero_hurt_{side}.png"
        elif not self._grounded():
            texture = f"hero_jump_{side}.png"
        elif abs(self.body.velocity_x) > 10:
            texture = f"hero_run{int(self.phase * 1.3) % 4}_{side}.png"
        else:
            texture = f"hero_idle{int(self.phase * 0.6) % 2}_{side}.png"
        self.hero.texture = str(self.assets / texture)
        self.hero.x = self.player.x
        self.hero.y = self.player.y + 8 + math.sin(self.phase) * (1.7 if self._grounded() else 0.5)
        self.hero_shadow.x = self.player.x
        self.hero_shadow.y = self.player.y - PLAYER_H / 2 - 5
        self.hero_shadow.width = 58 if self._grounded() else 42

        for index, (glow, sprite) in enumerate(self.shard_nodes):
            if not self.shard_active[index]:
                continue
            x, y = SHARDS[index]
            bob = math.sin(self.time * 4 + index) * 5
            glow.x, glow.y = x, y + bob
            glow.rotation += dt * 48
            sprite.x, sprite.y = x, y + bob
            sprite.rotation -= dt * 22
        for name, x, y in SIGILS:
            if name in self.collected_sigils:
                continue
            glow, sprite = self.sigil_nodes[name]
            bob = math.sin(self.time * 3.2 + x * 0.01) * 5
            glow.y, sprite.y = y + bob, y + bob
            glow.rotation += dt * 32
            sprite.rotation -= dt * 18

        self.archivist_glow.rotation += dt * 16
        unlocked = len(self.collected_sigils) == 3
        self.portal_glow.color = Color(0.20, 1.0, 0.76, 0.20 if self.boss_defeated else 0.05)
        self.portal.rotation = math.sin(self.time * 1.4) * 1.1
        if unlocked and not self.boss_defeated:
            self.gate_rune.color = Color(0.25, 1.0, 0.78, 1)

    def _camera_update(self) -> None:
        cam = self.game.camera
        target = max(WORLD_LEFT + W / 2, min(WORLD_RIGHT - W / 2, self.player.x))
        cam.x += (target - cam.x) * 0.10
        cam.y += ((self.player.y + 20) * 0.15 - cam.y) * 0.08
        self.sky.x, self.sky.y = cam.x, cam.y
        for i, node in enumerate(self.bg_far):
            node.x = cam.x * 0.12 - 1280 + i * 1280
        for i, node in enumerate(self.bg_mid):
            node.x = cam.x * 0.30 - 1280 + i * 1280
        for i, node in enumerate(self.bg_front):
            node.x = cam.x * 0.58 - 1280 + i * 1280

    def _ui_update(self) -> None:
        sigils = " ".join(symbol.upper() if symbol in self.collected_sigils else "---" for symbol, _x, _y in SIGILS)
        self.hud.text = f"HP {self.health}/5   SIGILS {len(self.collected_sigils)}/3   SHARDS {self.shards}"
        if self.player.x < -400:
            zone = "THE DROWNED RUINS"
        elif self.player.x < GATE_X:
            zone = "CRYSTAL CAVERNS"
        else:
            zone = "THE MOON TEMPLE"
        self.zone_label.text = zone
        if self.won:
            self.objective.text = "THE SHADOW RELIC IS YOURS"
            self.banner.text = "ADVENTURE COMPLETE"
        elif self.game_over:
            self.objective.text = "FALLEN — press R to return to the checkpoint"
            self.banner.text = "THE DARKNESS WON THIS ROUND"
        elif len(self.collected_sigils) < 3:
            self.objective.text = f"Find the three Moon Temple sigils   [{sigils}]"
            self.banner.text = ""
        elif not self.boss_defeated:
            self.objective.text = "Temple open — defeat the Shadow Warden"
            self.banner.text = ""
        else:
            self.objective.text = "Warden defeated — enter the relic portal"
            self.banner.text = ""
        if self.boss["alive"] and self.player.x > BOSS_ARENA_LEFT - 250:
            self.boss_label.text = f"SHADOW WARDEN   {'■' * int(self.boss['hp'])}"
        else:
            self.boss_label.text = ""

    def _new_game(self) -> None:
        self.checkpoint_index = 0
        self.collected_sigils.clear()
        self.boss_defeated = False
        self.shards = 0
        self.health = 5
        self.save.clear().save()
        for name, _x, _y in SIGILS:
            glow, sprite = self.sigil_nodes[name]
            glow.visible = sprite.visible = True
        self.shard_active[:] = [True] * len(SHARDS)
        for glow, sprite in self.shard_nodes:
            glow.visible = sprite.visible = True
        self.potion_active[:] = [True] * len(POTIONS)
        for node in self.potion_nodes:
            node.visible = True
        for i, enemy in enumerate(self.enemies):
            kind, x, y, patrol, speed, hp = ENEMY_SPECS[i]
            enemy.update({"origin": x, "base_y": y, "patrol": patrol, "speed": speed, "hp": hp, "alive": True, "direction": 1.0, "phase": 0.0})
            enemy["root"].x, enemy["root"].y = x, y
            enemy["collider"].enabled = True
            enemy["sprite"].visible = True
        self.boss.update({"hp": 7, "alive": True, "direction": 1.0, "phase": 0.0})
        self.boss["root"].x, self.boss["root"].y = 4260.0, -128.0
        self.boss["collider"].enabled = True
        self.boss["sprite"].visible = True
        self.won = False
        self.game_over = False
        self._reset_player(full=False)

    def _update(self, dt: float) -> None:
        self.frames += 1
        self.time += dt
        self.invulnerable = max(0.0, self.invulnerable - dt)
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        if self.game.key_pressed("N"):
            self._new_game()
        if self.game.key_pressed("R"):
            self._reset_player(full=False)
        if not self.won and not self.game_over:
            if self.game.key_pressed("SPACE") and self._grounded():
                self.body.velocity_y = JUMP_SPEED
                self.dust.x, self.dust.y = self.player.x, self.player.y - PLAYER_H / 2
                self.dust.burst(8)
                self._sound("jump.wav", 0.20)
            if self.game.key_pressed("X") or self.game.key_pressed("J"):
                self._attack()
            self._update_enemies(dt)
            self._contact_damage()
            self._collect()
            self._dialog_update(dt)
            if self.player.y < -430:
                self._damage()
        self._sync_visuals(dt)
        self._camera_update()
        self._ui_update()
        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES and self.frames < SMOKE_FRAMES:
            raise AssertionError("Shadow Relic 32 stopped before requested smoke frames")
        if SMOKE_FRAMES:
            print(f"Shadow Relic 32 smoke OK: frames={self.frames}, sigils={len(self.collected_sigils)}, hp={self.health}")


def main() -> None:
    if HEADLESS:
        print(f"Shadow Relic 32 headless OK: {run_headless_probe()}")
    else:
        ShadowRelic32().run()


if __name__ == "__main__":
    main()
