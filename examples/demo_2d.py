from swirengine import Color, Game, Rectangle2D

game = Game("SwirEngine 0.2 - 2D", 1000, 650)
player = game.add(
    Rectangle2D(0, 0, 150, 90, Color(0.1, 0.7, 1.0, 1.0), name="player", tags={"hero"})
)
enemy = game.add(
    Rectangle2D(250, 100, 100, 100, Color(1.0, 0.25, 0.35, 1.0), name="enemy")
)


@game.update
def update(dt):
    speed = 350.0
    if game.key("A"):
        player.x -= speed * dt
    if game.key("D"):
        player.x += speed * dt
    if game.key("W"):
        player.y += speed * dt
    if game.key("S"):
        player.y -= speed * dt
    enemy.rotation += 60.0 * dt


game.run()
