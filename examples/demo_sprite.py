from swirengine import Game, Sprite2D

game = Game("SwirEngine Sprite Demo", 1280, 720)
player = game.add(Sprite2D("assets/player.png", name="player", tags={"hero"}))


@game.update
def update(dt):
    speed = 300.0
    if game.key("A"):
        player.x -= speed * dt
    if game.key("D"):
        player.x += speed * dt
    if game.key("W"):
        player.y += speed * dt
    if game.key("S"):
        player.y -= speed * dt
    game.camera.follow(player)


game.run()
