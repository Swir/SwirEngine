from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from swirengine.animation15 import AnimationParameter, ParameterKind
from swirengine.editor_animation_project_resources22 import AnimationProjectResourceResolver22
from swirengine.editor_animation_state_machine22 import (
    AnimationMachineDocument22,
    AnimationStateNode22,
    AnimationTransitionSpec22,
    BlendChildSpec22,
    TransitionConditionSpec22,
)
from swirengine.editor_animation_workspace22 import AnimationMachineWorkspace22
from swirengine.graphics.gltf_skeletal import load_gltf_skeletal
from swirengine.graphics.skeletal import SkeletalAnimationClip3D, Skeleton3D


def _append(buffer: bytearray, array: np.ndarray) -> tuple[int, int]:
    while len(buffer) % 4:
        buffer.append(0)
    offset = len(buffer)
    payload = np.ascontiguousarray(array).tobytes()
    buffer.extend(payload)
    return offset, len(payload)


def _write_locomotion_gltf(path: Path) -> None:
    binary = bytearray()
    arrays = [
        np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype="<f4"),
        np.asarray(((0, 0, 1),) * 3, dtype="<f4"),
        np.asarray(((0, 1, 0, 0),) * 3, dtype="u1"),
        np.asarray(((255, 0, 0, 0),) * 3, dtype="u1"),
        np.asarray((0, 1, 2), dtype="<u2"),
        np.asarray((np.eye(4), np.eye(4)), dtype="<f4").transpose(0, 2, 1),
        np.asarray((0.0, 1.0), dtype="<f4"),
        np.asarray(((0, 1, 0), (1, 1, 0)), dtype="<f4"),
        np.asarray(((0, 1, 0), (3, 1, 0)), dtype="<f4"),
        np.asarray(((0, 1, 0), (0, 3, 0)), dtype="<f4"),
    ]
    views: list[dict[str, int]] = []
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
        {"bufferView": 8, "componentType": 5126, "count": 2, "type": "VEC3"},
        {"bufferView": 9, "componentType": 5126, "count": 2, "type": "VEC3"},
    ]
    encoded = base64.b64encode(binary).decode("ascii")
    animations = []
    for name, output in (("Walk", 7), ("Run", 8), ("Jump", 9)):
        animations.append(
            {
                "name": name,
                "samplers": [{"input": 6, "output": output, "interpolation": "LINEAR"}],
                "channels": [
                    {"sampler": 0, "target": {"node": 1, "path": "translation"}}
                ],
            }
        )
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
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                            "JOINTS_0": 2,
                            "WEIGHTS_0": 3,
                        },
                        "indices": 4,
                    }
                ]
            }
        ],
        "nodes": [
            {"name": "hero", "mesh": 0, "skin": 0, "children": [1]},
            {"name": "hips", "translation": [0, 1, 0]},
        ],
        "skins": [{"name": "hero-rig", "joints": [0, 1], "inverseBindMatrices": 5}],
        "animations": animations,
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def _locomotion_document() -> AnimationMachineDocument22:
    return AnimationMachineDocument22(
        states=(
            AnimationStateNode22(
                "Locomotion",
                blend_parameter="speed",
                blend_children=(
                    BlendChildSpec22(0.0, "walk"),
                    BlendChildSpec22(1.0, "run"),
                ),
            ),
            AnimationStateNode22("Jump", clip="jump", loop=False),
        ),
        parameters=(
            AnimationParameter("speed", ParameterKind.FLOAT),
            AnimationParameter("jump", ParameterKind.TRIGGER),
        ),
        transitions=(
            AnimationTransitionSpec22(
                "Locomotion",
                "Jump",
                conditions=(TransitionConditionSpec22("jump", "trigger"),),
                duration=0.15,
            ),
        ),
        initial="Locomotion",
    )


def test_project_resolver_loads_skeleton_and_named_clips_once(tmp_path: Path) -> None:
    source = tmp_path / "imports" / "hero.gltf"
    _write_locomotion_gltf(source)
    load_count = 0

    def counted_loader(path: str | Path):
        nonlocal load_count
        load_count += 1
        return load_gltf_skeletal(path)

    resolver = AnimationProjectResourceResolver22(tmp_path, loader=counted_loader)
    skeleton = resolver("imports/hero.gltf#skeleton")
    walk = resolver("imports/hero.gltf#clip:Walk")
    run = resolver("imports/hero.gltf#clip:Run")

    assert isinstance(skeleton, Skeleton3D)
    assert isinstance(walk, SkeletalAnimationClip3D)
    assert walk.name == "Walk"
    assert run.name == "Run"
    assert load_count == 1


def test_project_resolver_rejects_escape_bad_fragment_and_missing_clip(tmp_path: Path) -> None:
    source = tmp_path / "imports" / "hero.gltf"
    _write_locomotion_gltf(source)
    resolver = AnimationProjectResourceResolver22(tmp_path)

    with pytest.raises(ValueError, match="inside the project"):
        resolver("../outside.gltf#skeleton")
    with pytest.raises(ValueError, match="fragment"):
        resolver("imports/hero.gltf#mesh")
    with pytest.raises(KeyError, match="Missing"):
        resolver("imports/hero.gltf#clip:Missing")


def test_source_only_project_walk_run_jump_acceptance_gate(tmp_path: Path) -> None:
    source = tmp_path / "imports" / "hero.gltf"
    _write_locomotion_gltf(source)

    authored = AnimationMachineWorkspace22(tmp_path)
    authored.create("characters/hero", _locomotion_document())
    authored.configure_preview_resource_refs(
        "imports/hero.gltf#skeleton",
        {
            "walk": "imports/hero.gltf#clip:Walk",
            "run": "imports/hero.gltf#clip:Run",
            "jump": "imports/hero.gltf#clip:Jump",
        },
    )
    authored.save()

    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.open("characters/hero")
    workspace.resolve_preview_resources(AnimationProjectResourceResolver22(tmp_path))

    assert workspace.validate_runtime() == ()
    frame = workspace.start_preview()
    assert frame.preview_state == "Locomotion"
    workspace.controller.set_preview_parameter("speed", 1.0)
    frame = workspace.controller.step_preview(0.5)
    assert frame.rig[1].translation[0] == pytest.approx(1.5)

    workspace.controller.trigger_preview("jump")
    frame = workspace.controller.step_preview(0.0)
    assert frame.preview_next_state == "Jump"
    frame = workspace.controller.step_preview(0.15)
    assert frame.preview_state == "Jump"
