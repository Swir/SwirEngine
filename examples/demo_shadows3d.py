import swirengine

game = swirengine.Game("SwirEngine directional shadows", mode="3d", width=1100, height=700)
game.configure_shadows(resolution=2048, extent=14.0, distance=24.0)

material = swirengine.Material3D(
    tint=swirengine.Color(0.72, 0.36, 0.14, 1.0),
    ambient=0.18,
    diffuse=0.9,
    specular=0.2,
    shininess=48.0,
)

floor = game.mesh(swirengine.cube_mesh(), material=material, name="floor")
floor.position = swirengine.Vec3(0.0, -1.4, -7.0)
floor.scale = swirengine.Vec3(8.0, 0.35, 8.0)

caster = game.mesh(swirengine.cube_mesh(), material=material, name="caster")
caster.position = swirengine.Vec3(0.0, 0.0, -7.0)
caster.scale = swirengine.Vec3(1.8, 2.4, 1.8)

game.directional_light(
    direction=swirengine.Vec3(-0.65, -1.0, -0.45),
    color=swirengine.Color(1.0, 0.92, 0.8, 1.0),
    intensity=2.2,
)

game.camera.position = swirengine.Vec3(7.5, 5.5, 5.5)
game.camera.look_at(swirengine.Vec3(0.0, -0.2, -7.0))


@game.update
def animate(dt):
    caster.rotation.y += 25.0 * dt


game.run()
