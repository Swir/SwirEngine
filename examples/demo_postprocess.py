from swirengine import Color, Game


game = Game("SwirEngine Post-processing", 960, 540, mode="3d")
game.configure_postprocess(
    enabled=True,
    tone_mapping="aces",
    exposure=1.1,
    contrast=1.05,
    saturation=1.08,
    vignette=0.2,
    fxaa=True,
)

game.directional_light(direction=(0.4, -1.0, -0.3), intensity=2.0)
cube = game.mesh(
    __import__("swirengine").cube_mesh(),
    color=Color(0.25, 0.6, 1.0, 1.0),
)
cube.transform.position.z = -4.0


@game.update
def rotate_cube(dt: float) -> None:
    cube.transform.rotation.y += 35.0 * dt
    cube.transform.rotation.x += 18.0 * dt


game.run()
