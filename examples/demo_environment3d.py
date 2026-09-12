from swirengine import Environment3D, Game

game = Game(mode="3d", title="SwirEngine Environment 3D")
installation = Environment3D().install(
    game.scene,
    skybox_texture="assets/sky_panorama.jpg",
    skybox_size=80.0,
)


def update(_dt: float) -> None:
    installation.follow(game.camera)


game.on_update(update)
game.run()
