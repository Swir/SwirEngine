"""SwirEngine 2D Game Demo — an asset-free classic platformer showcase.

This source example intentionally uses only SwirEngine primitives and generated colors. It is
inspired by the classic side-scrolling platformer genre without copying any existing game's art,
levels, characters, names, sounds, or other assets.

Run from the repository root:
    python examples/2d_game_demo/run_game.py

Controls:
    A / D or Left / Right  Move
    Space                  Jump
    R                      Restart
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from swirengine import Color, Game, Rectangle2D

WIDTH = 960
HEIGHT = 540
HALF_W = WIDTH / 2.0
HALF_H = HEIGHT / 2.0
FIXED_DT = 1.0 / 120.0
SMOKE_FRAMES = int(os.environ.get("SWIR_GAME_DEMO_SMOKE_FRAMES", "0"))
HEADLESS = os.environ.get("SWIR_GAME_DEMO_HEADLESS") == "1"

PLAYER_W = 34.0
PLAYER_H = 48.0
PLAYER_SPEED = 300.0
JUMP_SPEED = 650.0
GRAVITY = -1800.0


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width / 2.0

    @property
    def bottom(self) -> float:
        return self.y - self.height / 2.0

    @property
    def top(self) -> float:
        return self.y + self.height / 2.0


@dataclass(slots=True)
class Enemy:
    x: float
    y: float
    origin_x: float
    patrol: float
    speed: float
    direction: float = 1.0


PLATFORMS = (
    Rect(-330.0, -245.0, 300.0, 50.0),
    Rect(0.0, -245.0, 260.0, 50.0),
    Rect(330.0, -245.0, 300.0, 50.0),
    Rect(-275.0, -120.0, 210.0, 28.0),
    Rect(5.0, -35.0, 210.0, 28.0),
    Rect(285.0, 55.0, 190.0, 28.0),
)
COINS = (
    (-330.0, -78.0),
    (-225.0, -78.0),
    (-45.0, 8.0),
    (55.0, 8.0),
    (245.0, 98.0),
    (325.0, 98.0),
)
GOAL = Rect(420.0, -166.0, 34.0, 108.0)
SPAWN_X = -420.0
SPAWN_Y = -196.0


def overlaps(x: float, y: float, width: float, height: float, rect: Rect) -> bool:
    return not (
        x + width / 2.0 <= rect.left
        or x - width / 2.0 >= rect.right
        or y + height / 2.0 <= rect.bottom
        or y - height / 2.0 >= rect.top
    )


class PlatformerState:
    """Small deterministic gameplay model shared by the live demo and CI headless probe."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.x = SPAWN_X
        self.y = SPAWN_Y
        self.vx = 0.0
        self.vy = 0.0
        self.grounded = True
        self.health = 3
        self.coin_active = [True] * len(COINS)
        self.enemies = [
            Enemy(25.0, -195.0, 25.0, 72.0, 72.0),
            Enemy(-275.0, -85.0, -275.0, 62.0, 58.0, -1.0),
            Enemy(285.0, 90.0, 285.0, 55.0, 68.0),
        ]
        self.hurt_cooldown = 0.0
        self.won = False
        self.lost = False

    @property
    def coins_collected(self) -> int:
        return len(COINS) - sum(self.coin_active)

    def _respawn(self) -> None:
        self.x = SPAWN_X
        self.y = SPAWN_Y
        self.vx = 0.0
        self.vy = 0.0
        self.grounded = True
        self.hurt_cooldown = 1.0

    def _resolve_horizontal(self, previous_x: float) -> None:
        for platform in PLATFORMS:
            if not overlaps(self.x, self.y, PLAYER_W, PLAYER_H, platform):
                continue
            if previous_x + PLAYER_W / 2.0 <= platform.left:
                self.x = platform.left - PLAYER_W / 2.0
            elif previous_x - PLAYER_W / 2.0 >= platform.right:
                self.x = platform.right + PLAYER_W / 2.0

    def _resolve_vertical(self, previous_y: float) -> None:
        self.grounded = False
        for platform in PLATFORMS:
            if not overlaps(self.x, self.y, PLAYER_W, PLAYER_H, platform):
                continue
            if self.vy <= 0.0 and previous_y - PLAYER_H / 2.0 >= platform.top - 2.0:
                self.y = platform.top + PLAYER_H / 2.0
                self.vy = 0.0
                self.grounded = True
            elif self.vy > 0.0 and previous_y + PLAYER_H / 2.0 <= platform.bottom + 2.0:
                self.y = platform.bottom - PLAYER_H / 2.0
                self.vy = 0.0

    def _update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            enemy.x += enemy.direction * enemy.speed * dt
            if enemy.x > enemy.origin_x + enemy.patrol:
                enemy.x = enemy.origin_x + enemy.patrol
                enemy.direction = -1.0
            elif enemy.x < enemy.origin_x - enemy.patrol:
                enemy.x = enemy.origin_x - enemy.patrol
                enemy.direction = 1.0

            hitbox = Rect(enemy.x, enemy.y, 38.0, 40.0)
            if self.hurt_cooldown <= 0.0 and overlaps(
                self.x, self.y, PLAYER_W, PLAYER_H, hitbox
            ):
                self.health -= 1
                if self.health <= 0:
                    self.lost = True
                    self.vx = self.vy = 0.0
                else:
                    self._respawn()
                return

    def _collect(self) -> None:
        for index, (coin_x, coin_y) in enumerate(COINS):
            if not self.coin_active[index]:
                continue
            if abs(self.x - coin_x) <= PLAYER_W / 2.0 + 12.0 and abs(self.y - coin_y) <= (
                PLAYER_H / 2.0 + 12.0
            ):
                self.coin_active[index] = False

        if self.coins_collected == len(COINS) and overlaps(
            self.x, self.y, PLAYER_W, PLAYER_H, GOAL
        ):
            self.won = True
            self.vx = self.vy = 0.0

    def step(self, move: float, jump: bool, dt: float) -> None:
        if self.won or self.lost:
            return
        dt = max(0.0, min(float(dt), 1.0 / 20.0))
        self.hurt_cooldown = max(0.0, self.hurt_cooldown - dt)

        move = max(-1.0, min(1.0, float(move)))
        self.vx = move * PLAYER_SPEED
        if jump and self.grounded:
            self.vy = JUMP_SPEED
            self.grounded = False

        previous_x = self.x
        self.x += self.vx * dt
        self._resolve_horizontal(previous_x)
        self.x = max(-HALF_W + PLAYER_W / 2.0, min(HALF_W - PLAYER_W / 2.0, self.x))

        previous_y = self.y
        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        self._resolve_vertical(previous_y)

        if self.y < -HALF_H - 100.0:
            self.health -= 1
            if self.health <= 0:
                self.lost = True
            else:
                self._respawn()
            return

        self._update_enemies(dt)
        self._collect()


def run_headless_probe() -> dict[str, float | int | bool]:
    state = PlatformerState()

    for _ in range(30):
        state.step(0.0, False, FIXED_DT)
    if not state.grounded or abs(state.y - SPAWN_Y) > 0.01:
        raise AssertionError("2D demo failed to settle on the starting platform")

    start_y = state.y
    state.step(0.0, True, FIXED_DT)
    peak = state.y
    for _ in range(90):
        state.step(0.0, False, FIXED_DT)
        peak = max(peak, state.y)
    if peak < start_y + 80.0:
        raise AssertionError("2D demo jump arc did not execute")

    for index, (coin_x, coin_y) in enumerate(COINS):
        state.x = coin_x
        state.y = coin_y
        state.vx = state.vy = 0.0
        state.coin_active[index] = True
        state._collect()
    if state.coins_collected != len(COINS):
        raise AssertionError("2D demo collectible loop did not collect every coin")

    state.x = GOAL.x
    state.y = GOAL.y
    state._collect()
    if not state.won:
        raise AssertionError("2D demo goal did not unlock after collecting all coins")

    return {
        "jump_height": round(peak - start_y, 3),
        "coins": state.coins_collected,
        "health": state.health,
        "won": state.won,
    }


class PlatformerDemo:
    def __init__(self) -> None:
        self.game = Game("SwirEngine 2D Game Demo", WIDTH, HEIGHT, target_fps=144)
        self.state = PlatformerState()
        self.frames = 0

        self.game.add(
            Rectangle2D(
                0.0,
                0.0,
                WIDTH,
                HEIGHT,
                Color(0.025, 0.045, 0.09, 1.0),
                name="night-sky",
                layer=-20,
            )
        )
        self.game.add(
            Rectangle2D(
                0.0,
                -215.0,
                WIDTH,
                110.0,
                Color(0.04, 0.08, 0.14, 1.0),
                name="horizon",
                layer=-10,
            )
        )

        platform_colors = (
            Color(0.08, 0.35, 0.55, 1.0),
            Color(0.08, 0.42, 0.62, 1.0),
            Color(0.08, 0.50, 0.68, 1.0),
        )
        for index, platform in enumerate(PLATFORMS):
            self.game.add(
                Rectangle2D(
                    platform.x,
                    platform.y,
                    platform.width,
                    platform.height,
                    platform_colors[index % len(platform_colors)],
                    name=f"platform-{index}",
                    tags={"platform"},
                )
            )

        self.goal = self.game.add(
            Rectangle2D(
                GOAL.x,
                GOAL.y,
                GOAL.width,
                GOAL.height,
                Color(0.25, 0.3, 0.35, 1.0),
                name="exit-gate",
            )
        )
        self.player = self.game.add(
            Rectangle2D(
                self.state.x,
                self.state.y,
                PLAYER_W,
                PLAYER_H,
                Color(0.1, 0.8, 1.0, 1.0),
                name="player",
                tags={"player"},
            )
        )
        self.coin_nodes = [
            self.game.add(
                Rectangle2D(
                    x,
                    y,
                    18.0,
                    18.0,
                    Color(1.0, 0.82, 0.15, 1.0),
                    rotation=45.0,
                    name=f"coin-{index}",
                    tags={"pickup"},
                )
            )
            for index, (x, y) in enumerate(COINS)
        ]
        self.enemy_nodes = [
            self.game.add(
                Rectangle2D(
                    enemy.x,
                    enemy.y,
                    38.0,
                    40.0,
                    Color(1.0, 0.25, 0.35, 1.0),
                    name=f"enemy-{index}",
                    tags={"enemy"},
                )
            )
            for index, enemy in enumerate(self.state.enemies)
        ]

        self.hud = self.game.label("", -350.0, 238.0, font_size=20)
        self.status = self.game.label("Collect every energy shard, then reach the gate.", 0.0, 238.0, font_size=18)
        self.help = self.game.label(
            "A/D or arrows: move | SPACE: jump | R: restart",
            0.0,
            -252.0,
            font_size=16,
        )
        self.game.update(self._update)
        self._sync_visuals()

    def _sync_visuals(self) -> None:
        self.player.x = self.state.x
        self.player.y = self.state.y
        self.player.color = (
            Color(1.0, 0.45, 0.25, 1.0)
            if self.state.hurt_cooldown > 0.0
            else Color(0.1, 0.8, 1.0, 1.0)
        )
        for node, active in zip(self.coin_nodes, self.state.coin_active, strict=True):
            node.visible = active
        for node, enemy in zip(self.enemy_nodes, self.state.enemies, strict=True):
            node.x = enemy.x
            node.y = enemy.y

        unlocked = self.state.coins_collected == len(COINS)
        self.goal.color = (
            Color(0.15, 1.0, 0.45, 1.0) if unlocked else Color(0.25, 0.3, 0.35, 1.0)
        )
        self.hud.text = (
            f"HP {self.state.health}   SHARDS {self.state.coins_collected}/{len(COINS)}"
        )
        if self.state.won:
            self.status.text = "LEVEL COMPLETE - press R to play again"
        elif self.state.lost:
            self.status.text = "GAME OVER - press R to restart"
        elif unlocked:
            self.status.text = "Gate unlocked - reach the green exit!"
        else:
            self.status.text = "Collect every energy shard, then reach the gate."

    def _update(self, dt: float) -> None:
        self.frames += 1
        if self.game.key_pressed("R"):
            self.state.reset()

        move = 0.0
        if self.game.key("A") or self.game.key("LEFT"):
            move -= 1.0
        if self.game.key("D") or self.game.key("RIGHT"):
            move += 1.0
        jump = self.game.key_pressed("SPACE")
        self.state.step(move, jump, dt)
        self._sync_visuals()

        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES and self.frames < SMOKE_FRAMES:
            raise AssertionError("2D game demo stopped before the requested smoke frame count")
        if SMOKE_FRAMES:
            print(
                "SwirEngine 2D Game Demo smoke OK: "
                f"frames={self.frames}, hp={self.state.health}, "
                f"coins={self.state.coins_collected}"
            )


def main() -> int:
    if HEADLESS:
        diagnostics = run_headless_probe()
        print(f"SwirEngine 2D Game Demo headless OK: {diagnostics}")
        return 0
    PlatformerDemo().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
