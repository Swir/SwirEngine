from swirengine import Game, Material3D, Vec3

game = Game("SwirEngine Textured 3D", mode="3d")
material = Material3D(
    texture=game.assets.require("models/crate.png"),
    ambient=0.3,
    diffuse=0.7,
)
crate = game.obj("models/crate.obj", material=material)
crate.position = Vec3(0.0, 0.0, -4.0)
game.camera.look_at(crate.position)


@game.update
def spin(dt):
    crate.rotation.y += 35.0 * dt


game.run()
