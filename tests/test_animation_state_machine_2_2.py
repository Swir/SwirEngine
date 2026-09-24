from __future__ import annotations

import json

import numpy as np
import pytest

from swirengine.animation15 import AnimationParameter, ParameterKind
from swirengine.animation_state_machine22 import (
    AnimationState22,
    AnimationStateMachine22,
    SkeletalBlendChild22,
    SkeletalBlendTree1D22,
)
from swirengine.editor_animation_state_machine22 import (
    ANIMATION_MACHINE_FORMAT22,
    AnimationMachineDocument22,
    AnimationMachineEditorSession22,
    AnimationStateNode22,
    AnimationTransitionSpec22,
    BlendChildSpec22,
    TransitionConditionSpec22,
)
from swirengine.graphics.skeletal import (
    SkeletalAnimationChannel,
    SkeletalAnimationClip3D,
    Skeleton3D,
    SkeletonNode3D,
)


def _skeleton() -> Skeleton3D:
    return Skeleton3D((SkeletonNode3D(0, name="root"),))


def _clip(name: str, *, x: float = 0.0, y: float = 0.0) -> SkeletalAnimationClip3D:
    channel = SkeletalAnimationChannel(
        node_index=0,
        path="translation",
        times=np.asarray([0.0, 1.0], dtype="f4"),
        values=np.asarray([[0.0, 0.0, 0.0], [x, y, 0.0]], dtype="f4"),
    )
    return SkeletalAnimationClip3D(name, (channel,))


def _creator_document() -> AnimationMachineDocument22:
    return AnimationMachineDocument22(
        states=(
            AnimationStateNode22(
                "Locomotion",
                x=80.0,
                y=140.0,
                blend_parameter="speed",
                blend_children=(
                    BlendChildSpec22(0.0, "walk"),
                    BlendChildSpec22(1.0, "run"),
                ),
            ),
            AnimationStateNode22("Jump", x=420.0, y=140.0, clip="jump", loop=False),
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


def test_blend_tree_samples_real_skeletal_clips() -> None:
    skeleton = _skeleton()
    walk = _clip("walk", x=1.0)
    run = _clip("run", x=3.0)
    state = AnimationState22(
        "Locomotion",
        SkeletalBlendTree1D22(
            "speed",
            (
                SkeletalBlendChild22(0.0, walk),
                SkeletalBlendChild22(1.0, run),
            ),
        ),
    )
    machine = AnimationStateMachine22(
        skeleton,
        (state,),
        parameters=(AnimationParameter("speed", ParameterKind.FLOAT, 0.5),),
    )

    player = machine.player()
    player.update(0.5)

    assert player.sample().translations[0][0] == pytest.approx(1.0)


def test_creator_walk_run_jump_flow_blends_and_consumes_trigger() -> None:
    skeleton = _skeleton()
    clips = {
        "walk": _clip("walk", x=1.0),
        "run": _clip("run", x=3.0),
        "jump": _clip("jump", y=2.0),
    }
    player = _creator_document().compile(skeleton, clips).player()
    player.set_parameter("speed", 1.0)

    locomotion = player.update(0.5)
    assert locomotion.translations[0][0] == pytest.approx(1.5)
    assert player.current == "Locomotion"

    player.trigger("jump")
    transition_start = player.update(0.0)
    assert player.transitioning
    assert player.next_state == "Jump"
    assert player.parameters.get("jump") is False
    assert transition_start.translations[0][0] == pytest.approx(1.5)

    midpoint = player.update(0.1)
    assert midpoint.translations[0][0] == pytest.approx(0.9)
    assert midpoint.translations[0][1] == pytest.approx(0.1)

    player.update(0.1)
    assert player.current == "Jump"
    assert not player.transitioning


def test_visual_asset_round_trip_is_deterministic_and_preserves_canvas(tmp_path) -> None:
    document = _creator_document()
    session = AnimationMachineEditorSession22.create(tmp_path, "hero", document)
    session.move_state("Jump", 512.0, 96.0)
    target = session.save()

    assert target.name == "hero.swiranimgraph"
    first = target.read_text(encoding="utf-8")
    payload = json.loads(first)
    assert payload["format"] == ANIMATION_MACHINE_FORMAT22
    assert payload["states"][1]["position"] == [512.0, 96.0]
    assert session.dirty is False

    reopened = AnimationMachineEditorSession22.open(tmp_path, "hero")
    reopened.save()
    assert target.read_text(encoding="utf-8") == first
    assert reopened.document.states[1].x == pytest.approx(512.0)


def test_document_rejects_assets_outside_project(tmp_path) -> None:
    session = AnimationMachineEditorSession22.create(
        tmp_path,
        "../escape",
        _creator_document(),
    )
    with pytest.raises(ValueError, match="inside the project"):
        session.save()


def test_document_compile_rejects_unknown_clip_reference() -> None:
    with pytest.raises(KeyError, match="unknown clip"):
        _creator_document().compile(
            _skeleton(),
            {
                "walk": _clip("walk", x=1.0),
                "run": _clip("run", x=3.0),
            },
        )


def test_blend_tree_rejects_duplicate_thresholds() -> None:
    clip = _clip("walk", x=1.0)
    with pytest.raises(ValueError, match="unique"):
        SkeletalBlendTree1D22(
            "speed",
            (
                SkeletalBlendChild22(0.0, clip),
                SkeletalBlendChild22(0.0, clip),
            ),
        )
