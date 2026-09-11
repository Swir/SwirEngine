import swirengine

game = swirengine.Game("SwirEngine 3D Lighting", 1100, 700, mode="3d")
game.camera.position = swirengine.Vec3(0.0, 2.5, 7.0)
game.camera.look_at(swirengine.Vec3(0.0, 0.0, 0.0))

material = swirengine.Material3D(
    tint=swirengine.Color(0.65, 0.8, 1.0, 1.0),
    ambient=0.12,
    diffuse=0.8,
    specular=0.65,
    shininess=48.0,
)
model = game.mesh(
    swirengine.cube_mesh(),
    material=material,
    scale=swirengine.Vec3(2.0, 2.0, 2.0),
)

game.directional_light(
    direction=swirengine.Vec3(-0.4, -1.0, -0.3),
    color=swirengine.Color(1.0, 0.95, 0.85, 1.0),
    intensity=0.7,
)
game.point_light(
    position=swirengine.Vec3(2.5, 2.0, 2.0),
    color=swirengine.Color(0.35, 0.55, 1.0, 1.0),
    intensity=2.0,
    range=8.0,
)
game.spot_light(
    position=swirengine.Vec3(-2.5, 3.0, 2.0),
    direction=swirengine.Vec3(0.6, -0.8, -0.4),
    color=swirengine.Color(1.0, 0.35, 0.25, 1.0),
    intensity=3.0,
    range=10.0,
    inner_angle=18.0,
    outer_angle=30.0,
)


@game.update
def rotate(dt: float) -> None:
    model.rotation.y += 35.0 * dt
    model.rotation.x += 12.0 * dt


game.run()
