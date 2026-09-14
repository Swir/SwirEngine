import base64
import json
from pathlib import Path

import numpy as np
import pytest

from swirengine import load_gltf
from swirengine.graphics.mesh import MeshData
from swirengine.skeletal import (
    MAX_SKIN_JOINTS,
    Skeleton3D,
    SkeletonNode3D,
    SkeletalAnimationChannel,
    SkeletalAnimationClip3D,
    SkeletalAnimationController,
    Skin3D,
    SkinnedMesh3D,
    SkinnedMeshData,
    blend_skeletal_poses,
    load_gltf_skeletal,
    quaternion_slerp,
    sample_skeletal_clip,
    skin_joint_palette,
)


def _skeleton() -> Skeleton3D:
    return Skeleton3D(
        (
            SkeletonNode3D(0, name="root"),
            SkeletonNode3D(1, parent=0, name="hand", translation=(0.0, 1.0, 0.0)),
        )
    )


def _skin() -> Skin3D:
    inverse = np.repeat(np.eye(4, dtype="f4")[None], 2, axis=0)
    inverse[1, 1, 3] = -1.0
    return Skin3D((0, 1), inverse, mesh_node_index=0)


def test_linear_translation_and_quaternion_slerp_are_normalized():
    skeleton = _skeleton()
    move = SkeletalAnimationChannel(
        1,
        "translation",
        np.asarray((0.0, 1.0), dtype="f4"),
        np.asarray(((0.0, 1.0, 0.0), (2.0, 1.0, 0.0)), dtype="f4"),
    )
    rotate = SkeletalAnimationChannel(
        1,
        "rotation",
        np.asarray((0.0, 1.0), dtype="f4"),
        np.asarray(((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 0.0)), dtype="f4"),
    )
    pose = sample_skeletal_clip(
        skeleton,
        SkeletalAnimationClip3D("move", (move, rotate)),
        0.5,
    )
    assert pose.translations[1] == pytest.approx((1.0, 1.0, 0.0))
    assert float(np.linalg.norm(pose.rotations[1])) == pytest.approx(1.0)
    assert quaternion_slerp((0, 0, 0, 1), (0, 0, -1, 0), 0.5)[3] > 0.0


def test_step_and_cubic_spline_channels_follow_gltf_contract():
    step = SkeletalAnimationChannel(
        0,
        "scale",
        np.asarray((0.0, 1.0), dtype="f4"),
        np.asarray(((1.0, 1.0, 1.0), (3.0, 3.0, 3.0)), dtype="f4"),
        "STEP",
    )
    cubic_values = np.asarray(
        (
            ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
            ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ),
        dtype="f4",
    )
    cubic = SkeletalAnimationChannel(
        0,
        "translation",
        np.asarray((0.0, 1.0), dtype="f4"),
        cubic_values,
        "CUBICSPLINE",
    )
    assert step.sample(0.75) == pytest.approx((1.0, 1.0, 1.0))
    assert cubic.sample(0.5)[0] == pytest.approx(0.5)


def test_joint_palette_is_identity_in_bind_pose_and_moves_with_joint():
    skeleton = _skeleton()
    skin = _skin()
    bind_palette = skin_joint_palette(skeleton, skin, skeleton.bind_pose())
    assert bind_palette == pytest.approx(np.repeat(np.eye(4)[None], 2, axis=0))

    channel = SkeletalAnimationChannel(
        1,
        "translation",
        np.asarray((0.0, 1.0), dtype="f4"),
        np.asarray(((0.0, 1.0, 0.0), (1.0, 1.0, 0.0)), dtype="f4"),
    )
    pose = sample_skeletal_clip(
        skeleton, SkeletalAnimationClip3D("move", (channel,)), 1.0, loop=False
    )
    palette = skin_joint_palette(skeleton, skin, pose)
    assert palette[1, 0, 3] == pytest.approx(1.0)


def test_crossfade_blends_from_previous_clip_without_pose_pop():
    skeleton = _skeleton()
    idle = SkeletalAnimationClip3D("idle", ())
    move = SkeletalAnimationClip3D(
        "move",
        (
            SkeletalAnimationChannel(
                1,
                "translation",
                np.asarray((0.0, 1.0), dtype="f4"),
                np.asarray(((0.0, 1.0, 0.0), (2.0, 1.0, 0.0)), dtype="f4"),
            ),
        ),
    )
    controller = SkeletalAnimationController(skeleton, {"idle": idle, "move": move})
    controller.play("idle")
    controller.play("move", fade=1.0)
    controller.update(0.5)
    assert controller.pose().translations[1] == pytest.approx((0.5, 1.0, 0.0))
    controller.update(0.5)
    assert not controller.blending


def test_pose_blend_rejects_different_skeleton_sizes():
    one = Skeleton3D((SkeletonNode3D(0),)).bind_pose()
    two = _skeleton().bind_pose()
    with pytest.raises(ValueError, match="different node counts"):
        blend_skeletal_poses(one, two, 0.5)


def test_skinned_mesh_normalizes_weights_and_enforces_joint_table():
    mesh = MeshData(
        np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype="f4"),
        np.asarray(((0, 0, 1),) * 3, dtype="f4"),
    )
    data = SkinnedMeshData(
        mesh,
        np.asarray(((0, 1, 0, 0),) * 3, dtype="i4"),
        np.asarray(((1.0, 1.0, 0.0, 0.0),) * 3, dtype="f4"),
    )
    assert data.weights[0] == pytest.approx((0.5, 0.5, 0.0, 0.0))
    obj = SkinnedMesh3D(data, _skeleton(), _skin())
    assert obj.vertex_count == 3

    bad = SkinnedMeshData(
        mesh,
        np.asarray(((0, 2, 0, 0),) * 3, dtype="i4"),
        np.asarray(((1.0, 1.0, 0.0, 0.0),) * 3, dtype="f4"),
    )
    with pytest.raises(ValueError, match="joint index"):
        SkinnedMesh3D(bad, _skeleton(), _skin())


def test_skin_rejects_gpu_joint_budget_overflow():
    matrices = np.repeat(np.eye(4, dtype="f4")[None], MAX_SKIN_JOINTS + 1, axis=0)
    with pytest.raises(ValueError, match="joint budget"):
        Skin3D(tuple(range(MAX_SKIN_JOINTS + 1)), matrices, 0)


def _append(buffer: bytearray, array: np.ndarray) -> tuple[int, int]:
    while len(buffer) % 4:
        buffer.append(0)
    offset = len(buffer)
    payload = np.ascontiguousarray(array).tobytes()
    buffer.extend(payload)
    return offset, len(payload)


def _write_skeletal_gltf(path: Path) -> None:
    binary = bytearray()
    arrays = [
        np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype="<f4"),
        np.asarray(((0, 0, 1),) * 3, dtype="<f4"),
        np.asarray(((0, 1, 0, 0),) * 3, dtype="u1"),
        np.asarray(((255, 0, 0, 0), (128, 127, 0, 0), (0, 255, 0, 0)), dtype="u1"),
        np.asarray((0, 1, 2), dtype="<u2"),
        np.asarray((np.eye(4), np.eye(4)), dtype="<f4").transpose(0, 2, 1),
        np.asarray((0.0, 1.0), dtype="<f4"),
        np.asarray(((0, 1, 0), (1, 1, 0)), dtype="<f4"),
    ]
    views = []
    for array in arrays:
        offset, length = _append(binary, array)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": length})
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
        {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
        {"bufferView": 2, "componentType": 5121, "count": 3, "type": "VEC4"},
        {"bufferView": 3, "componentType": 5121, "normalized": True, "count": 3, "type": "VEC4"},
        {"bufferView": 4, "componentType": 5123, "count": 3, "type": "SCALAR"},
        {"bufferView": 5, "componentType": 5126, "count": 2, "type": "MAT4"},
        {"bufferView": 6, "componentType": 5126, "count": 2, "type": "SCALAR"},
        {"bufferView": 7, "componentType": 5126, "count": 2, "type": "VEC3"},
    ]
    encoded = base64.b64encode(binary).decode("ascii")
    document = {
        "asset": {"version": "2.0"},
        "buffers": [
            {
                "uri": f"data:application/octet-stream;base64,{encoded}",
                "byteLength": len(binary),
            }
        ],
        "bufferViews": views,
        "accessors": accessors,
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "JOINTS_0": 2, "WEIGHTS_0": 3},
                        "indices": 4,
                    }
                ]
            }
        ],
        "nodes": [
            {"name": "mesh", "mesh": 0, "skin": 0, "children": [1]},
            {"name": "joint", "translation": [0, 1, 0]},
        ],
        "skins": [{"name": "rig", "joints": [0, 1], "inverseBindMatrices": 5}],
        "animations": [
            {
                "name": "wave",
                "samplers": [{"input": 6, "output": 7, "interpolation": "LINEAR"}],
                "channels": [{"sampler": 0, "target": {"node": 1, "path": "translation"}}],
            }
        ],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def test_gltf_skeletal_loader_reads_skin_weights_and_animation(tmp_path: Path):
    source = tmp_path / "rig.gltf"
    _write_skeletal_gltf(source)
    asset = load_gltf_skeletal(source)
    assert asset.clip_names == ("wave",)
    assert len(asset.objects) == 1
    obj = asset.objects[0]
    assert obj.skin.joints == (0, 1)
    assert obj.data.weights[0] == pytest.approx((1.0, 0.0, 0.0, 0.0))
    assert obj.data.weights[1, :2].sum() == pytest.approx(1.0)
    obj.play("wave")
    obj.update(0.5)
    assert obj.controller.pose().translations[1] == pytest.approx((0.5, 1.0, 0.0))


def test_static_gltf_loader_contract_remains_separate(tmp_path: Path):
    source = tmp_path / "rig.gltf"
    _write_skeletal_gltf(source)
    asset = load_gltf_skeletal(source)
    assert isinstance(asset.objects[0], SkinnedMesh3D)
    static_mesh = load_gltf(source)
    assert static_mesh.vertex_count == 3
