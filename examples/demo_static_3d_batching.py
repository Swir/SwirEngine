from swirengine import Color, Cube3D, Game, Vec3

from swirengine.graphics.static_batch import build_static_cube_batches


game = Game("Static 3D batching", 1280, 720, mode="3d")

cubes = [
    Cube3D(
        position=Vec3((index % 20) - 10.0, (index // 20) * 1.1 - 2.0, -12.0),
        color=Color(0.15, 0.7, 1.0, 1.0),
    )
    for index in range(200)
]

batch = build_static_cube_batches(cubes)
for mesh in batch.meshes:
    game.add(mesh)

game.camera.position = Vec3(0.0, 3.0, 8.0)
game.camera.look_at(Vec3(0.0, 2.0, -12.0))

print(
    f"Static cubes: {batch.metrics.source_objects} -> "
    f"{batch.metrics.draw_calls_after} draw call(s), "
    f"reduction {batch.metrics.draw_call_reduction:.1%}"
)

game.run()
