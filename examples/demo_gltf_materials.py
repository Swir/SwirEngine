from pathlib import Path

from swirengine import Game, Mesh3D, Vec3, load_gltf_primitives

ASSET = Path("assets/models/material_demo.gltf")

game = Game("SwirEngine glTF materials", mode="3d")

for index, primitive in enumerate(load_gltf_primitives(ASSET)):
    model = Mesh3D(
        primitive.mesh,
        material=primitive.material,
        position=Vec3(index * 1.5, 0.0, -5.0),
    )
    game.add(model)

game.camera.look_at(Vec3(0.0, 0.0, -5.0))
game.run()
