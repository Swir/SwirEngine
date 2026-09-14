from swirengine import Color, Game, InstancedCube3D, Material3D, Vec3

game = Game(
    "SwirEngine GPU instancing smoke",
    640,
    360,
    mode="3d",
    vsync=False,
    target_fps=240,
)
game.camera.position = Vec3(0.0, 5.0, 12.0)
game.camera.look_at(Vec3(0.0, 0.0, -8.0))

batch = InstancedCube3D(
    color=Color(0.1, 0.75, 1.0, 1.0),
    material=Material3D(metallic=0.2, roughness=0.45),
)
for z in range(20):
    for x in range(20):
        batch.add_cube(
            position=Vec3((x - 10) * 1.1, 0.0, -3.0 - z * 1.1),
            size=0.72,
        )

game.add(batch)
game.directional_light(direction=Vec3(-0.5, -1.0, -0.4), intensity=2.0)

frames = 0


@game.update
def stop_after_render_probe(dt: float) -> None:
    global frames
    frames += 1
    if frames >= 5:
        game.stop()


game.run()
assert frames >= 5
print(f"GPU instancing OpenGL smoke rendered {batch.instance_count} source instances.")
