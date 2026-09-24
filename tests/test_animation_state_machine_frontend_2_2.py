from __future__ import annotations

import numpy as np
import pytest

from swirengine.animation15 import AnimationParameter, ParameterKind
from swirengine.editor_animation_state_machine22 import (
    AnimationMachineDocument22,
    AnimationMachineEditorSession22,
    AnimationStateNode22,
    AnimationTransitionSpec22,
    BlendChildSpec22,
    TransitionConditionSpec22,
)
from swirengine.editor_animation_state_machine_frontend22 import (
    AnimationMachinePanelController22,
)
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
    channel = SkeletalAnimationChannel(
        node_index=1,
        path="translation",
        times=np.asarray([0.0, 1.0], dtype="f4"),
        values=np.asarray([[0.0, 0.0, 0.0], [x, y, 0.0]], dtype="f4"),
    )
    return SkeletalAnimationClip3D(name, (channel,))


def _document() -> AnimationMachineDocument22:
    return AnimationMachineDocument22(
        states=(
            AnimationStateNode22(
                "Locomotion",
                x=80.0,
                y=120.0,
                blend_parameter="speed",
                blend_children=(
                    BlendChildSpec22(0.0, "walk"),
                    BlendChildSpec22(1.0, "run"),
                ),
            ),
            AnimationStateNode22("Jump", x=420.0, y=120.0, clip="jump", loop=False),
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
                duration=0.2,
                priority=10,
            ),
        ),
        initial="Locomotion",
    )


def _controller(tmp_path) -> AnimationMachinePanelController22:
    session = AnimationMachineEditorSession22.create(tmp_path, "hero", _document())
    return AnimationMachinePanelController22(session)


def test_graph_authoring_renames_states_and_rewires_transition(tmp_path) -> None:
    controller = _controller(tmp_path)

    frame = controller.rename_state("Jump", "Airborne")
    controller.move_state("Airborne", 540.0, 90.0)
    controller.set_initial("Airborne")

    assert frame.selected_state == "Airborne"
    assert controller.session.document.transitions[0].target == "Airborne"
    assert controller.session.document.initial == "Airborne"
    assert controller.selected_state.x == pytest.approx(540.0)
    assert controller.selected_state.y == pytest.approx(90.0)
    assert controller.session.dirty is True


def test_parameter_inspector_renames_references_and_guards_removal(tmp_path) -> None:
    controller = _controller(tmp_path)

    controller.rename_parameter("speed", "move_speed")
    document = controller.session.document

    assert document.parameters[0].name == "move_speed"
    assert document.states[0].blend_parameter == "move_speed"
    with pytest.raises(ValueError, match="used by blend state"):
        controller.remove_parameter("move_speed")

    controller.add_parameter("grounded", "bool", True)
    controller.set_parameter_default("grounded", False)
    assert controller.session.document.parameters[-1].default is False


def test_transition_editor_validates_conditions_and_supports_updates(tmp_path) -> None:
    controller = _controller(tmp_path)
    controller.add_clip_state("Land", "walk", x=680.0, y=120.0)
    controller.add_parameter("grounded", "bool", False)

    frame = controller.add_transition(
        "Jump",
        "Land",
        conditions=(TransitionConditionSpec22("grounded", "true"),),
        duration=0.15,
        exit_time=0.6,
        priority=5,
    )
    index = len(frame.transitions) - 1
    frame = controller.update_transition(index, duration=0.25, priority=8)

    row = frame.transitions[index]
    assert row.source == "Jump"
    assert row.target == "Land"
    assert row.duration == pytest.approx(0.25)
    assert row.exit_time == pytest.approx(0.6)
    assert row.priority == 8
    assert row.conditions == ("grounded true",)

    with pytest.raises(ValueError, match="self-transitions"):
        controller.add_transition("Land", "Land")
    with pytest.raises(KeyError, match="unknown animation state"):
        controller.add_transition("Land", "Missing")


def test_runtime_preview_exposes_parameters_transition_debug_and_rig(tmp_path) -> None:
    controller = _controller(tmp_path)
    skeleton = _skeleton()
    clips = {
        "walk": _clip("walk", x=1.0),
        "run": _clip("run", x=3.0),
        "jump": _clip("jump", y=2.0),
    }

    frame = controller.start_preview(skeleton, clips)
    assert frame.preview_active is True
    assert frame.preview_state == "Locomotion"
    assert [node.name for node in frame.rig] == ["root", "hips"]

    controller.set_preview_parameter("speed", 1.0)
    frame = controller.step_preview(0.5)
    hips = frame.rig[1]
    assert hips.translation[0] == pytest.approx(1.5)
    assert dict(frame.preview_parameters)["speed"] == pytest.approx(1.0)

    controller.trigger_preview("jump")
    frame = controller.step_preview(0.0)
    assert frame.preview_state == "Locomotion"
    assert frame.preview_next_state == "Jump"
    assert dict(frame.preview_parameters)["jump"] is False

    frame = controller.step_preview(0.2)
    assert frame.preview_state == "Jump"
    assert frame.preview_next_state is None


def test_edit_invalidates_stale_preview_but_retains_resources_for_restart(tmp_path) -> None:
    controller = _controller(tmp_path)
    skeleton = _skeleton()
    clips = {
        "walk": _clip("walk", x=1.0),
        "run": _clip("run", x=3.0),
        "jump": _clip("jump", y=2.0),
    }
    controller.start_preview(skeleton, clips)

    frame = controller.configure_clip_state("Jump", "jump", speed=1.25)
    assert frame.preview_active is False

    frame = controller.restart_preview()
    assert frame.preview_active is True
    assert frame.preview_state == "Locomotion"


def test_runtime_validation_reports_unknown_clip_without_mutating_asset(tmp_path) -> None:
    controller = _controller(tmp_path)
    issues = controller.validate_runtime(
        _skeleton(),
        {
            "walk": _clip("walk", x=1.0),
            "run": _clip("run", x=3.0),
        },
    )

    assert any("unknown clip" in issue for issue in issues)
    assert controller.session.dirty is True


def test_save_preserves_creator_graph_and_clears_dirty_flag(tmp_path) -> None:
    controller = _controller(tmp_path)
    controller.rename_state("Jump", "Airborne")
    frame = controller.save()

    assert frame.dirty is False
    reopened = AnimationMachineEditorSession22.open(tmp_path, "hero")
    assert [state.name for state in reopened.document.states] == ["Locomotion", "Airborne"]
    assert reopened.document.transitions[0].target == "Airborne"
