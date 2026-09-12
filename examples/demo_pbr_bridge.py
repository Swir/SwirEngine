import swirengine as sw


game = sw.Game("SwirEngine PBR Bridge", 1100, 700, mode="3d")

rough_metal = game.mesh(
    sw.cube_mesh(),
    position=sw.Vec3(-1.6, 0.0, -5.0),
    material=sw.Material3D(
        tint=sw.Color(0.8, 0.45, 0.18, 1.0),
        metallic=0.9,
        roughness=0.7,
    ),
)

smooth_dielectric = game.mesh(
    sw.cube_mesh(),
    position=sw.Vec3(1.6, 0.0, -5.0),
    material=sw.Material3D(
        tint=sw.Color(0.15, 0.55, 0.95, 1.0),
        metallic=0.0,
        roughness=0.18,
    ),
)

game.directional_light(direction=sw.Vec3(-0.4, -1.0, -0.3), intensity=0.7)
game.point_light(position=sw.Vec3(0.0, 2.2, -2.5), intensity=2.0, range=8.0)
game.camera.position = sw.Vec3(0.0, 1.0, 2.0)
game.camera.look_at(sw.Vec3(0.0, 0.0, -5.0))


@game.update
def spin(dt):
    rough_metal.rotation.y += 24.0 * dt
    smooth_dielectric.rotation.y -= 32.0 * dt


game.run()
