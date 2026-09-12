import swirengine


game = swirengine.Game("SwirEngine PBR", mode="3d", width=1100, height=700)

surfaces = (
    ("rough dielectric", -2.4, 0.0, 0.85),
    ("smooth dielectric", -0.8, 0.0, 0.18),
    ("rough metal", 0.8, 1.0, 0.72),
    ("smooth metal", 2.4, 1.0, 0.12),
)
models = []

for name, x, metallic, roughness in surfaces:
    model = game.mesh(
        swirengine.cube_mesh(),
        material=swirengine.Material3D(
            tint=swirengine.Color(0.82, 0.35, 0.12, 1.0),
            ambient=0.04,
            metallic=metallic,
            roughness=roughness,
        ),
        name=name,
    )
    model.position = swirengine.Vec3(x, 0.0, -6.0)
    models.append(model)

game.directional_light(
    direction=swirengine.Vec3(-0.5, -1.0, -0.4),
    color=swirengine.Color(1.0, 0.92, 0.82, 1.0),
    intensity=2.0,
)
game.point_light(
    position=swirengine.Vec3(0.0, 2.5, -3.0),
    color=swirengine.Color(0.55, 0.72, 1.0, 1.0),
    intensity=8.0,
    range=9.0,
)
game.camera.position = swirengine.Vec3(0.0, 1.2, 2.0)
game.camera.look_at(swirengine.Vec3(0.0, 0.0, -6.0))


@game.update
def animate(dt):
    for model in models:
        model.rotation.y += 25.0 * dt


game.run()
