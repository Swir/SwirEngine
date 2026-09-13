from swirengine import Color, Game, Rectangle2D


game = Game("SwirEngine Gamepad Demo", 960, 540, mode="2d")
player = game.add(Rectangle2D(-40, -40, 80, 80, Color(0.15, 0.75, 1.0, 1.0)))
status = game.label("Connect a mapped gamepad or use WASD", 24, 24)


@game.update
def update(dt: float) -> None:
    x, y = game.input.gamepad_stick("left")

    # Keyboard fallback keeps the same gameplay code usable without a controller.
    if not game.input.gamepad_connected():
        x = float(game.key("D")) - float(game.key("A"))
        y = float(game.key("S")) - float(game.key("W"))
        status.value = "Keyboard fallback: WASD"
    else:
        status.value = f"Gamepad: {game.input.gamepad_name()} | A = boost"

    speed = 520.0 if game.input.gamepad_button("A") else 300.0
    player.x += x * speed * dt
    player.y += y * speed * dt

    if game.input.gamepad_button_pressed("START"):
        player.x = -40.0
        player.y = -40.0


game.run()
