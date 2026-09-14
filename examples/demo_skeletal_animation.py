import numpy as np

from swirengine import Color, Game, Material3D, Vec3
from swirengine.graphics.mesh import MeshData
from swirengine.skeletal import (
    SkeletalAnimationChannel,
    SkeletalAnimationClip3D,
    Skeleton3D,
    SkeletonNode3D,
    Skin3D,
    SkinnedMesh3D,
    SkinnedMeshData,
)

mesh = MeshData(
    np.asarray(((-1.2, -1.0, 0.0), (1.2, -1.0, 0.0), (0.0, 1.6, 0.0)), dtype="f4"),
    np.asarray(((0.0, 0.0, 1.0),) * 3, dtype="f4"),
)
skeleton = Skeleton3D(
    (
        SkeletonNode3D(0, name="root"),
        SkeletonNode3D(1, parent=0, name="upper", translation=(0.0, 0.5, 0.0)),
    )
)
inverse_bind = np.repeat(np.eye(4, dtype="f4")[None], 2, axis=0)
inverse_bind[1, 1, 3] = -0.5
skin = Skin3D((0, 1), inverse_bind, mesh_node_index=0)
data = SkinnedMeshData(
    mesh,
    np.asarray(((0, 1, 0, 0), (0, 1, 0, 0), (1, 0, 0, 0)), dtype="i4"),
    np.asarray(((0.8, 0.2, 0, 0), (0.2, 0.8, 0, 0), (1, 0, 0, 0)), dtype="f4"),
)
clip = SkeletalAnimationClip3D(
    "Sway",
    (
        SkeletalAnimationChannel(
            1,
            "rotation",
            np.asarray((0.0, 0.75, 1.5), dtype="f4"),
            np.asarray(
                (
                    (0.0, 0.0, -0.342, 0.940),
                    (0.0, 0.0, 0.342, 0.940),
                    (0.0, 0.0, -0.342, 0.940),
                ),
                dtype="f4",
            ),
        ),
    ),
)
character = SkinnedMesh3D(
    data,
    skeleton,
    skin,
    {"Sway": clip},
    position=Vec3(0.0, 0.0, -5.0),
    color=Color(0.15, 0.75, 1.0, 1.0),
    material=Material3D(metallic=0.1, roughness=0.4),
)
character.play("Sway")

game = Game("SwirEngine 1.3 - Skeletal Animation", 1100, 700, mode="3d")
game.camera.position = Vec3(0.0, 0.0, 3.0)
game.camera.look_at(Vec3(0.0, 0.0, -5.0))
game.add(character)
game.directional_light(direction=Vec3(-0.4, -1.0, -0.5), intensity=2.0)
game.show_debug(True)
game.run()
