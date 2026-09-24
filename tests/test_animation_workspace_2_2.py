from __future__ import annotations

import numpy as np
import pytest

from swirengine.animation15 import AnimationParameter, ParameterKind
from swirengine.editor_animation_state_machine22 import (
    AnimationMachineDocument22,
    AnimationStateNode22,
    AnimationTransitionSpec22,
    BlendChildSpec22,
    TransitionConditionSpec22,
)
from swirengine.editor_animation_workspace22 import AnimationMachineWorkspace22
from swirengine.editor_animation_workspace_frontend22 import TkAnimationMachineEditorApp22
from swirengine.editor_asset_app21 import TkIntegratedEditorApp21
from swirengine.graphics.skeletal import (
    SkeletalAnimationChannel,
    SkeletalAnimationClip3D,
    Skeleton3D,
    SkeletonNode3D,
)


def _skeleton() -> Skeleton3D:
    return Skeleton3D(
        (
            SkeletonNode3D(0, name="root"),
            SkeletonNode3D(1, parent=0, name="hips"),
        )
    )


def _clip(name: str, *, x: float = 0.0, y: float = 0.0) -> SkeletalAnimationClip3D:
    return SkeletalAnimationClip3D(
        name,
        (
            SkeletalAnimationChannel(
                node_index=1,
                path="translation",
                times=np.asarray([0.0, 1.0], dtype="f4"),
                values=np.asarray([[0.0, 0.0, 0.0], [x, y, 0.0]], dtype="f4"),
            ),
        ),
    )


def _locomotion_document() -> AnimationMachineDocument22:
    return AnimationMachineDocument22(
        states=(
            AnimationStateNode22(
                "Locomotion",
                x=120.0,
                y=160.0,
                blend_parameter="speed",
                blend_children=(
                    BlendChildSpec22(0.0, "walk"),
                    BlendChildSpec22(1.0, "run"),
                ),
            ),
            AnimationStateNode22("Jump", x=440.0, y=160.0, clip="jump", loop=False),
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


def test_workspace_discovers_nested_assets_deterministically(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.create("zeta", _locomotion_document())
    workspace.save()
    workspace.create("characters/Hero", _locomotion_document())
    workspace.save()
    workspace.create("alpha", _locomotion_document())
    workspace.save()

    assert workspace.discover() == (
        "alpha.swiranimgraph",
        "characters/Hero.swiranimgraph",
        "zeta.swiranimgraph",
    )


def test_workspace_rejects_paths_outside_project(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)

    with pytest.raises(ValueError, match="inside the project"):
        workspace.create("../outside", _locomotion_document())
    with pytest.raises(ValueError, match="inside the project"):
        workspace.open("../outside")


def test_workspace_roundtrip_keeps_active_dirty_state(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    frame = workspace.create("hero", _locomotion_document())
    assert frame.dirty is True
    assert workspace.snapshot().active_asset == "hero"

    workspace.controller.move_state("Jump", 520.0, 90.0)
    frame = workspace.save()
    assert frame.dirty is False
    assert workspace.dirty is False

    reopened = AnimationMachineWorkspace22(tmp_path)
    frame = reopened.open("hero")
    jump = next(state for state in frame.states if state.name == "Jump")
    assert jump.x == pytest.approx(520.0)
    assert jump.y == pytest.approx(90.0)


def test_workspace_binds_shipping_runtime_for_walk_run_jump_preview(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.create("hero", _locomotion_document())
    workspace.bind_preview_resources(
        _skeleton(),
        {
            "walk": _clip("walk", x=1.0),
            "run": _clip("run", x=3.0),
            "jump": _clip("jump", y=2.0),
        },
    )

    assert workspace.validate_runtime() == ()
    frame = workspace.start_preview()
    assert frame.preview_state == "Locomotion"
    workspace.controller.set_preview_parameter("speed", 1.0)
    frame = workspace.controller.step_preview(0.5)
    assert frame.rig[1].translation[0] == pytest.approx(1.5)

    workspace.controller.trigger_preview("jump")
    frame = workspace.controller.step_preview(0.0)
    assert frame.preview_state == "Locomotion"
    assert frame.preview_next_state == "Jump"
    frame = workspace.controller.step_preview(0.15)
    assert frame.preview_state == "Jump"


def test_workspace_requires_real_preview_resources(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.create("hero", _locomotion_document())

    assert workspace.validate_runtime() == ("preview resources are not bound",)
    with pytest.raises(RuntimeError, match="not bound"):
        workspace.start_preview()
    with pytest.raises(ValueError, match="at least one"):
        workspace.bind_preview_resources(_skeleton(), {})


def test_integrated_editor_routes_through_animation_workspace_frontend() -> None:
    assert issubclass(TkIntegratedEditorApp21, TkAnimationMachineEditorApp22)
