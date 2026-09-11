from swirengine import Color, Game, Rectangle2D

game = Game("SwirEngine Collision Demo", 1000, 650)
player = game.add(Rectangle2D(-200, 0, 80, 80, Color(0.1, 0.7, 1.0, 1.0)))
wall = game.add(Rectangle2D(100, 0, 100, 260, Color(1.0, 0.3, 0.3, 1.0)))
player_collider = game.collider(player, tag="player")
game.collider(wall, tag="wall")


@game.update
def update(dt):
    previous_x = player.x
    if game.key("A"):
        player.x -= 250 * dt
    if game.key("D"):
        player.x += 250 * dt
    if game.collisions.query(player_collider, tag="wall"):
        player.x = previous_x


game.run()
