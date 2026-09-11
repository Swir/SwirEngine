from swirengine import Game, Rectangle2D, Color

game = Game("SwirEngine 0.1 - 2D", 1000, 650, mode="2d")
player = Rectangle2D(0, 0, 150, 90, Color(0.1, 0.7, 1.0, 1.0))
enemy = Rectangle2D(250, 100, 100, 100, Color(1.0, 0.25, 0.35, 1.0))
game.scene.add(player)
game.scene.add(enemy)

@game.update
def update(dt):
    speed = 350.0
    if game.input.key("A"):
        player.x -= speed * dt
    if game.input.key("D"):
        player.x += speed * dt
    if game.input.key("W"):
        player.y += speed * dt
    if game.input.key("S"):
        player.y -= speed * dt
    enemy.rotation += 60.0 * dt

game.run()
