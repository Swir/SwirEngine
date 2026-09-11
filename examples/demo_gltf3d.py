from swirengine import Game, Vec3

game = Game("SwirEngine glTF Viewer", mode="3d", width=1280, height=720)
model = game.gltf("models/model.gltf")
model.position = Vec3(0.0, 0.0, -4.0)
game.camera.look_at(model.position)
game.show_debug()


@game.update
def move_camera(dt: float) -> None:
    speed = 3.5 * dt
    if game.key("W"):
        game.camera.move_local(forward=speed)
    if game.key("S"):
        game.camera.move_local(forward=-speed)
    if game.key("A"):
        game.camera.move_local(right=-speed)
    if game.key("D"):
        game.camera.move_local(right=speed)


game.run()
