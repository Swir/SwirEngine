from swirengine import AnimatedSprite2D, Game, SpriteSheet

game = Game("SwirEngine Animation Demo", 1280, 720)
sheet = SpriteSheet(columns=6, rows=2)
player = AnimatedSprite2D(game.assets.resolve("hero_sheet.png"), width=96, height=96)
player.add_animation("idle", sheet.row(0), fps=6)
player.add_animation("walk", sheet.row(1), fps=12)
game.add(player)


@game.update
def update(dt):
    speed = 300.0
    moving = False
    if game.key("A"):
        player.x -= speed * dt
        moving = True
    if game.key("D"):
        player.x += speed * dt
        moving = True
    player.play("walk" if moving else "idle")
    game.camera.follow(player)


game.run()
