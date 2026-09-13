"""Asset-free survival sample with spawning, scoring and scene bulk cleanup.

Run with:
    python examples/sample_dodge_arena.py
"""

from __future__ import annotations

import random

from swirengine import Color, Game, Rectangle2D

WIDTH = 960
HEIGHT = 540
HALF_W = WIDTH / 2
HALF_H = HEIGHT / 2
PLAYER_SPEED = 460.0

rng = random.Random(7)
game = Game("SwirEngine Dodge Arena", WIDTH, HEIGHT, target_fps=144)

player = game.add(
    Rectangle2D(
        0,
        -HALF_H + 52,
        42,
        42,
        Color(0.2, 0.85, 1.0, 1.0),
        name="player",
        tags={"player"},
    )
)
score_label = game.label("Score: 0", -HALF_W + 100, HALF_H - 35, font_size=22)
lives_label = game.label("Lives: 3", HALF_W - 100, HALF_H - 35, font_size=22)
message_label = game.label("Survive! Move with A/D or arrows", 0, 0, font_size=25)

enemy_speeds: dict[int, float] = {}
score = 0.0
lives = 3
spawn_timer = 0.0
invulnerable = 0.0


def overlaps(a: Rectangle2D, b: Rectangle2D) -> bool:
    return (
        abs(a.x - b.x) * 2 < a.width + b.width
        and abs(a.y - b.y) * 2 < a.height + b.height
    )


def spawn_enemy() -> None:
    size = rng.uniform(24.0, 58.0)
    x = rng.uniform(-HALF_W + size, HALF_W - size)
    speed = rng.uniform(170.0, 280.0) + min(score * 0.12, 190.0)
    enemy = game.add(
        Rectangle2D(
            x,
            HALF_H + size,
            size,
            size,
            Color(1.0, rng.uniform(0.2, 0.55), 0.25, 1.0),
            name="hazard",
            tags={"enemy", "hazard"},
        )
    )
    enemy_speeds[id(enemy)] = speed


def clear_enemies() -> None:
    for enemy in game.scene.remove_tagged("enemy"):
        enemy_speeds.pop(id(enemy), None)


def reset_round() -> None:
    global invulnerable
    clear_enemies()
    player.x = 0
    invulnerable = 1.5


@game.update
def update(dt: float) -> None:
    global invulnerable, lives, score, spawn_timer

    direction = 0
    if game.key("A") or game.key("LEFT"):
        direction -= 1
    if game.key("D") or game.key("RIGHT"):
        direction += 1
    player.x += direction * PLAYER_SPEED * dt
    min_x = -HALF_W + player.width / 2
    max_x = HALF_W - player.width / 2
    player.x = max(min_x, min(max_x, player.x))

    score += dt * 10.0
    score_label.text = f"Score: {int(score)}"
    invulnerable = max(0.0, invulnerable - dt)

    spawn_timer -= dt
    if spawn_timer <= 0.0:
        spawn_enemy()
        spawn_timer = max(0.18, 0.68 - score / 1800.0)

    offscreen: list[Rectangle2D] = []
    hit = False
    for obj in game.scene.tagged("enemy"):
        if not isinstance(obj, Rectangle2D):
            continue
        obj.y -= enemy_speeds.get(id(obj), 220.0) * dt
        if obj.y < -HALF_H - obj.height:
            offscreen.append(obj)
        elif invulnerable <= 0.0 and overlaps(player, obj):
            hit = True

    if offscreen:
        game.scene.remove_many(*offscreen)
        for enemy in offscreen:
            enemy_speeds.pop(id(enemy), None)

    if hit:
        lives -= 1
        lives_label.text = f"Lives: {lives}"
        if lives <= 0:
            lives = 3
            score = 0.0
            lives_label.text = "Lives: 3"
            message_label.text = "New round!"
        else:
            message_label.text = "Hit! Keep moving"
        reset_round()

    message_label.visible = score < 35.0 or invulnerable > 1.0


game.run()
