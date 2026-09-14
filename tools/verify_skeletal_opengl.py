import numpy as np

from swirengine import Color, Game, Material3D, Vec3
from swirengine.graphics.mesh import MeshData
from swirengine.skeletal import (
    Skeleton3D,
    SkeletonNode3D,
    SkeletalAnimationChannel,
    SkeletalAnimationClip3D,
    Skin3D,
    SkinnedMesh3D,
    SkinnedMeshData,
)

mesh = MeshData(
    np.asarray(((-1.4, -0.8, 0.0), (1.4, -0.8, 0.0), (0.0, 1.6, 0.0)), dtype="f4"),
    np.asarray(((0.0, 0.0, 1.0),) * 3, dtype="f4"),
    np.asarray(((0.0, 0.0), (1.0, 0.0), (0.5, 1.0)), dtype="f4"),
)
skeleton = Skeleton3D(
    (
        SkeletonNode3D(0, name="root"),
        SkeletonNode3D(1, parent=0, name="tip", translation=(0.0, 0.8, 0.0)),
    )
)
inverse_bind = np.repeat(np.eye(4, dtype="f4")[None], 2, axis=0)
inverse_bind[1, 1, 3] = -0.8
skin = Skin3D((0, 1), inverse_bind, mesh_node_index=0)
data = SkinnedMeshData(
    mesh,
    np.asarray(((0, 1, 0, 0), (0, 1, 0, 0), (1, 0, 0, 0)), dtype="i4"),
    np.asarray(((0.8, 0.2, 0, 0), (0.2, 0.8, 0, 0), (1, 0, 0, 0)), dtype="f4"),
)
clip = SkeletalAnimationClip3D(
    "sway",
    (
        SkeletalAnimationChannel(
            1,
            "rotation",
            np.asarray((0.0, 0.5, 1.0), dtype="f4"),
            np.asarray(
                (
                    (0.0, 0.0, -0.258819, 0.965926),
                    (0.0, 0.0, 0.258819, 0.965926),
                    (0.0, 0.0, -0.258819, 0.965926),
                ),
                dtype="f4",
            ),
        ),
    ),
)
obj = SkinnedMesh3D(
    data,
    skeleton,
    skin,
    {"sway": clip},
    position=Vec3(0.0, 0.0, -5.0),
    color=Color(0.2, 0.75, 1.0, 1.0),
    material=Material3D(metallic=0.15, roughness=0.42),
)
obj.play("sway")

game = Game("SwirEngine skeletal GPU smoke", 640, 360, mode="3d", vsync=False, target_fps=240)
game.camera.position = Vec3(0.0, 0.0, 3.5)
game.camera.look_at(Vec3(0.0, 0.0, -5.0))
game.add(obj)
game.directional_light(direction=Vec3(-0.4, -1.0, -0.5), intensity=2.0)
frames = 0


@game.update
def stop_after_gpu_skinning_probe(dt: float) -> None:
    global frames
    frames += 1
    if frames >= 5:
        game.stop()


game.run()
assert frames >= 5
assert obj.controller.time > 0.0
print(f"Skeletal GPU skinning smoke rendered {obj.vertex_count} animated vertices.")
