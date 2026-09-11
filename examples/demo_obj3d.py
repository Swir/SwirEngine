from swirengine import Game, Vec3

game = Game("SwirEngine OBJ Viewer", mode="3d")
model = game.obj("models/model.obj")
model.position = Vec3(0.0, 0.0, -4.0)
game.camera.move(0.0, 1.0, 2.0).look_at(model.position)


@game.update
def update(dt):
    model.rotation.y += 30.0 * dt
    speed = 3.0 * dt
    if game.key("W"):
        game.camera.move_local(forward=speed)
    if game.key("S"):
        game.camera.move_local(forward=-speed)
    if game.key("A"):
        game.camera.move_local(right=-speed)
    if game.key("D"):
        game.camera.move_local(right=speed)


game.run()
