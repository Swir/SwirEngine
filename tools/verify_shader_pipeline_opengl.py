from swirengine import Color, Game, ShaderMesh3D, Vec3, cube_mesh, shader_material_3d

game = Game(
    "SwirEngine shader material smoke",
    640,
    360,
    mode="3d",
    vsync=False,
    target_fps=240,
)
game.camera.position = Vec3(0.0, 2.5, 7.0)
game.camera.look_at(Vec3(0.0, 0.0, -4.0))

material = shader_material_3d(
    hooks={
        "fragment_globals": "uniform float pulse;",
        "fragment_surface": (
            "surface_rgba.rgb *= vec3(0.35 + 0.65 * pulse, 0.85, 1.0 - 0.25 * pulse);"
        ),
    },
    uniforms={"pulse": 0.8},
)
mesh = cube_mesh()
for index, x in enumerate((-1.6, 0.0, 1.6)):
    game.add(
        ShaderMesh3D(
            mesh,
            material,
            position=Vec3(x, 0.0, -4.0),
            rotation=Vec3(15.0, index * 25.0, 0.0),
            color=Color(0.25, 0.75, 1.0, 1.0),
        )
    )

game.directional_light(direction=Vec3(-0.4, -1.0, -0.5), intensity=1.6)
frames = 0


@game.update
def stop_after_render_probe(dt: float) -> None:
    global frames
    frames += 1
    material.set_uniform("pulse", 0.45 + (frames % 3) * 0.2)
    if frames >= 5:
        game.stop()


game.run()
assert frames >= 5
print("Shader material OpenGL smoke rendered a cached custom variant for five frames.")
