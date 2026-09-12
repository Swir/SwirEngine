from swirengine import Color, Game, Material3D, Vec3, cube_mesh


game = Game("SwirEngine PBR", mode="3d", width=1100, height=700)

metals = (
    ("rough dielectric", -2.4, 0.0, 0.85),
    ("smooth dielectric", -0.8, 0.0, 0.18),
    ("rough metal", 0.8, 1.0, 0.72),
    ("smooth metal", 2.4, 1.0, 0.12),
)

for name, x, metallic, roughness in metals:
    model = game.mesh(
        cube_mesh(),
        material=Material3D(
            tint=Color(0.82, 0.35, 0.12, 1.0),
            ambient=0.04,
            metallic=metallic,
            roughness=roughness,
        ),
        name=name,
    )
    model.position = Vec3(x, 0.0, -6.0)

sun = game.directional_light(
    direction=Vec3(-0.5, -1.0, -0.4),
    color=Color(1.0, 0.92, 0.82, 1.0),
    intensity=2.0,
)
key = game.point_light(
    position=Vec3(0.0, 2.5, -3.0),
    color=Color(0.55, 0.72, 1.0, 1.0),
    intensity=8.0,
    range=9.0,
)
game.camera.position = Vec3(0.0, 1.2, 2.0)
game.camera.look_at(Vec3(0.0, 0.0, -6.0))


@game.update
def animate(dt):
    for item in game.scene.objects:
        if getattr(item, "name", "") in {entry[0] for entry in metals}:
            item.rotation.y += 25.0 * dt
    key.position.x = 2.5
    sun.intensity = 2.0


game.run()
