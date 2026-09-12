from swirengine import Color, Game, Vec3, cube_mesh

game = Game("SwirEngine Post-processing", 960, 540, mode="3d")
game.camera.position = Vec3(0.0, 1.5, 6.0)
game.camera.look_at(Vec3(0.0, 0.0, 0.0))
game.configure_postprocess(
    enabled=True,
    tone_mapping="aces",
    exposure=1.1,
    contrast=1.05,
    saturation=1.08,
    vignette=0.2,
    fxaa=True,
)

game.directional_light(
    direction=Vec3(0.4, -1.0, -0.3),
    intensity=2.0,
)
cube = game.mesh(
    cube_mesh(),
    color=Color(0.25, 0.6, 1.0, 1.0),
    scale=Vec3(2.0, 2.0, 2.0),
)


@game.update
def rotate_cube(dt: float) -> None:
    cube.rotation.y += 35.0 * dt
    cube.rotation.x += 18.0 * dt


game.run()
