"""Asset-free Breakout-style sample that exercises the creator-facing 2D API.

Run with:
    python examples/sample_breakout.py
"""

from __future__ import annotations

from swirengine import Color, Game, Rectangle2D

WIDTH = 960
HEIGHT = 540
HALF_W = WIDTH / 2
HALF_H = HEIGHT / 2


def overlaps(a: Rectangle2D, b: Rectangle2D) -> bool:
    return (
        abs(a.x - b.x) * 2 < a.width + b.width
        and abs(a.y - b.y) * 2 < a.height + b.height
    )


game = Game("SwirEngine Breakout", WIDTH, HEIGHT, target_fps=144)

paddle = game.add(
    Rectangle2D(
        0,
        -HALF_H + 45,
        150,
        22,
        Color(0.2, 0.75, 1.0, 1.0),
        name="paddle",
        tags={"player"},
    )
)
ball = game.add(
    Rectangle2D(
        0,
        -80,
        18,
        18,
        Color(1.0, 0.9, 0.25, 1.0),
        name="ball",
        tags={"ball"},
    )
)
score_label = game.label("Score: 0", -HALF_W + 100, HALF_H - 35, font_size=22)
level_label = game.label("Level: 1", HALF_W - 105, HALF_H - 35, font_size=22)
help_label = game.label("A/D or arrows to move", 0, -HALF_H + 18, font_size=17)

velocity = [285.0, 285.0]
score = 0
level = 1


def build_bricks(current_level: int) -> None:
    game.scene.remove_tagged("brick")
    columns = 10
    rows = min(4 + current_level, 8)
    brick_w = 78
    brick_h = 24
    gap = 9
    total_w = columns * brick_w + (columns - 1) * gap
    start_x = -total_w / 2 + brick_w / 2
    start_y = HALF_H - 82

    palette = (
        Color(1.0, 0.35, 0.35, 1.0),
        Color(1.0, 0.65, 0.25, 1.0),
        Color(0.95, 0.9, 0.25, 1.0),
        Color(0.35, 0.9, 0.45, 1.0),
        Color(0.35, 0.65, 1.0, 1.0),
        Color(0.75, 0.45, 1.0, 1.0),
    )
    for row in range(rows):
        for column in range(columns):
            game.add(
                Rectangle2D(
                    start_x + column * (brick_w + gap),
                    start_y - row * (brick_h + gap),
                    brick_w,
                    brick_h,
                    palette[row % len(palette)],
                    name=f"brick-{row}-{column}",
                    tags={"brick", "destructible"},
                )
            )


def reset_ball() -> None:
    ball.x = paddle.x
    ball.y = paddle.y + 45
    velocity[0] = 285.0 if level % 2 else -285.0
    velocity[1] = 285.0 + min(level * 16.0, 130.0)


build_bricks(level)


@game.update
def update(dt: float) -> None:
    global level, score

    direction = 0
    if game.key("A") or game.key("LEFT"):
        direction -= 1
    if game.key("D") or game.key("RIGHT"):
        direction += 1
    paddle.x += direction * 520.0 * dt
    paddle.x = max(-HALF_W + paddle.width / 2, min(HALF_W - paddle.width / 2, paddle.x))

    previous_y = ball.y
    ball.x += velocity[0] * dt
    ball.y += velocity[1] * dt

    if ball.x - ball.width / 2 <= -HALF_W or ball.x + ball.width / 2 >= HALF_W:
        velocity[0] *= -1.0
        ball.x = max(-HALF_W + ball.width / 2, min(HALF_W - ball.width / 2, ball.x))
    if ball.y + ball.height / 2 >= HALF_H:
        velocity[1] = -abs(velocity[1])

    if velocity[1] < 0 and overlaps(ball, paddle) and previous_y >= paddle.y:
        offset = (ball.x - paddle.x) / max(paddle.width / 2, 1.0)
        velocity[0] = max(-430.0, min(430.0, velocity[0] + offset * 120.0))
        velocity[1] = abs(velocity[1])
        ball.y = paddle.y + paddle.height / 2 + ball.height / 2 + 1

    hit = next((brick for brick in game.scene.tagged("brick") if overlaps(ball, brick)), None)
    if isinstance(hit, Rectangle2D):
        game.remove(hit)
        velocity[1] *= -1.0
        score += 100
        score_label.text = f"Score: {score}"

    if ball.y < -HALF_H - 30:
        score = max(0, score - 250)
        score_label.text = f"Score: {score}"
        reset_ball()

    if not game.scene.tagged("brick"):
        level += 1
        level_label.text = f"Level: {level}"
        build_bricks(level)
        reset_ball()

    help_label.visible = level == 1 and score == 0


game.run()
