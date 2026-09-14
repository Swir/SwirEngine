from swirengine import Color, Game, InstancedCube3D, Material3D, Vec3

game = Game("SwirEngine 1.3 - GPU Instancing", 1280, 720, mode="3d")
game.camera.position = Vec3(0.0, 18.0, 32.0)
game.camera.look_at(Vec3(0.0, 0.0, -24.0))

field = InstancedCube3D(
    color=Color(0.12, 0.75, 1.0, 1.0),
    material=Material3D(metallic=0.15, roughness=0.38),
    name="instanced-neon-field",
)

for z in range(80):
    for x in range(80):
        distance = abs(x - 40) + abs(z - 18)
        tint = Color(
            0.12 + min(0.45, distance * 0.004),
            0.45 + min(0.45, z * 0.005),
            1.0,
            1.0,
        )
        field.add_cube(
            position=Vec3((x - 40) * 1.25, -2.0, -z * 1.25),
            size=0.82,
            color=tint,
        )

game.add(field)
game.directional_light(
    direction=Vec3(-0.5, -1.0, -0.35),
    color=Color(0.8, 0.9, 1.0, 1.0),
    intensity=2.0,
)
game.point_light(
    position=Vec3(0.0, 5.0, -18.0),
    color=Color(0.1, 0.7, 1.0, 1.0),
    intensity=8.0,
    range=35.0,
)
game.show_debug(True)

print(f"Created {field.instance_count:,} dynamic cube instances in one instanced batch.")
print("Move the camera in code to see CPU frustum culling change the submitted instance count.")

game.run()
