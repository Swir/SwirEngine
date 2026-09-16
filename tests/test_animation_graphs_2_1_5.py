from dataclasses import dataclass, field

import pytest

from swirengine.animation15 import (
    AnimationClip,
    AnimationCondition,
    AnimationGraph2,
    AnimationGraphPlayer,
    AnimationKeyframe,
    AnimationParameter,
    AnimationPose,
    AnimationState2,
    AnimationTrack,
    AnimationTransition2,
    ConditionOperator,
    InterpolationMode,
    ParameterKind,
)


def track(binding: str, start: float, end: float, *, duration: float = 1.0) -> AnimationTrack:
    return AnimationTrack(
        binding,
        (
            AnimationKeyframe(0.0, start),
            AnimationKeyframe(duration, end),
        ),
    )


def clip(name: str, start: float, end: float, *, duration: float = 1.0) -> AnimationClip:
    return AnimationClip(name, duration, (track("x", start, end, duration=duration),))


def test_track_samples_linear_and_step_keyframes() -> None:
    linear = AnimationTrack(
        "x",
        (
            AnimationKeyframe(0.0, 0.0),
            AnimationKeyframe(1.0, 10.0),
            AnimationKeyframe(2.0, 30.0),
        ),
    )
    step = AnimationTrack(
        "state",
        (
            AnimationKeyframe(0.0, "idle"),
            AnimationKeyframe(1.0, "run"),
        ),
        InterpolationMode.STEP,
    )
    assert linear.sample(0.5) == pytest.approx(5.0)
    assert linear.sample(1.5) == pytest.approx(20.0)
    assert step.sample(0.75) == "idle"
    assert step.sample(1.0) == "run"


def test_clip_clamps_or_loops_and_pose_can_apply_nested_binding() -> None:
    animation = AnimationClip(
        "move",
        2.0,
        (
            AnimationTrack(
                "transform.position",
                (
                    AnimationKeyframe(0.0, [0.0, 0.0, 0.0]),
                    AnimationKeyframe(2.0, [10.0, 4.0, 0.0]),
                ),
            ),
        ),
    )
    assert animation.sample(3.0).values["transform.position"] == pytest.approx([10.0, 4.0, 0.0])
    assert animation.sample(3.0, loop=True).values["transform.position"] == pytest.approx(
        [5.0, 2.0, 0.0]
    )

    @dataclass
    class Actor:
        transform: dict[str, object] = field(
            default_factory=lambda: {"position": [0.0, 0.0, 0.0]}
        )

    actor = Actor()
    animation.sample(1.0).apply(actor)
    assert actor.transform["position"] == pytest.approx([5.0, 2.0, 0.0])


def test_pose_blending_is_deterministic_and_portable() -> None:
    first = AnimationPose({"x": 0.0, "alpha": 1.0})
    second = AnimationPose({"x": 10.0, "alpha": 0.0})
    blended = first.blend(second, 0.25)
    assert blended.values == {"x": pytest.approx(2.5), "alpha": pytest.approx(0.75)}
    assert blended.fingerprint() == AnimationPose({"alpha": 0.75, "x": 2.5}).fingerprint()


def test_parameters_are_typed_and_triggers_are_explicit() -> None:
    graph = AnimationGraph2(
        [AnimationState2("idle", clip("idle", 0.0, 0.0))],
        parameters=(
            AnimationParameter("grounded", ParameterKind.BOOL, True),
            AnimationParameter("speed", ParameterKind.FLOAT),
            AnimationParameter("combo", ParameterKind.INT),
            AnimationParameter("jump", ParameterKind.TRIGGER),
        ),
    )
    player = AnimationGraphPlayer(graph)
    player.set_parameter("speed", 3)
    player.set_parameter("combo", 2)
    player.trigger("jump")
    assert player.parameters.get("speed") == pytest.approx(3.0)
    assert player.parameters.get("combo") == 2
    assert player.parameters.get("jump") is True
    with pytest.raises(TypeError):
        player.set_parameter("combo", 2.5)
    with pytest.raises(TypeError):
        player.trigger("grounded")


def test_graph_uses_priority_and_crossfade_blending() -> None:
    graph = AnimationGraph2(
        [
            AnimationState2("idle", clip("idle", 0.0, 0.0)),
            AnimationState2("walk", clip("walk", 10.0, 20.0)),
            AnimationState2("run", clip("run", 100.0, 200.0)),
        ],
        parameters=(AnimationParameter("speed", ParameterKind.FLOAT),),
        transitions=(
            AnimationTransition2(
                "idle",
                "walk",
                (AnimationCondition("speed", ConditionOperator.GT, 0.1),),
                duration=1.0,
                priority=10,
            ),
            AnimationTransition2(
                "idle",
                "run",
                (AnimationCondition("speed", ConditionOperator.GT, 3.0),),
                duration=1.0,
                priority=100,
            ),
        ),
    )
    player = AnimationGraphPlayer(graph)
    player.set_parameter("speed", 5.0)
    pose = player.update(0.0)
    assert player.current_state == "idle"
    assert player.next_state == "run"
    assert pose.values["x"] == pytest.approx(0.0)
    pose = player.update(0.5)
    assert pose.values["x"] == pytest.approx(75.0)
    pose = player.update(0.5)
    assert player.current_state == "run"
    assert player.next_state is None
    assert pose.values["x"] == pytest.approx(100.0)


def test_zero_duration_transition_switches_immediately_and_consumes_trigger() -> None:
    graph = AnimationGraph2(
        [
            AnimationState2("ground", clip("ground", 0.0, 0.0)),
            AnimationState2("jump", clip("jump", 50.0, 60.0), loop=False),
        ],
        parameters=(AnimationParameter("jump", ParameterKind.TRIGGER),),
        transitions=(
            AnimationTransition2(
                "ground",
                "jump",
                (AnimationCondition("jump", ConditionOperator.TRIGGGER),),
            ),
        ),
    )
    player = AnimationGraphPlayer(graph)
    player.trigger("jump")
    pose = player.update(0.0)
    assert player.current_state == "jump"
    assert player.parameters.get("jump") is False
    assert pose.values["x"] == pytest.approx(50.0)
    assert player.transitions_taken == 1


def test_exit_time_gates_transition_until_source_progress_is_reached() -> None:
    graph = AnimationGraph2(
        [
            AnimationState2("attack", clip("attack", 0.0, 10.0, duration=2.0), loop=False),
            AnimationState2("idle", clip("idle", 20.0, 20.0)),
        ],
        transitions=(AnimationTransition2("attack", "idle", exit_time=0.75),),
        initial="attack",
   )
    player = AnimationGraphPlayer(graph)
    player.update(1.0)
    assert player.current_state == "attack"
    player.update(0.49)
    assert player.current_state == "attack"
    player.update(0.01)
    assert player.current_state == "idle"


def test_wildcard_transition_and_bool_condition() -> None:
    graph = AnimationGraph2(
        [
            AnimationState2("idle", clip("idle", 0.0, 0.0)),
            AnimationState2("run", clip("run", 1.0, 2.0)),
            AnimationState2("dead", clip("dead", -1.0, -1.0), loop=False),
        ],
        parameters=(AnimationParameter("dead", ParameterKind.BOOL),),
        transitions=(
            AnimationTransition2(
                "*",
                "dead",
                (AnimationCondition("speed", ConditionOperator.TRUE),),
                priority=1000,
            ),
        ),
    )
    player = AnimationGraphPlayer(graph)
    player.force_state("run")
    player.set_parameter("dead", True)
    player.update(0.0)
    assert player.current_state == "dead"


def test_graph_validation_rejects_bad_state_transition_and_condition_contracts() -> None:
    idle = AnimationState2("idle", clip("idle", 0.0, 0.0))
    with pytest.raises(ValueError):
        AnimationGraph2([idle, idle])
    with pytest.raises(KeyError):
        AnimationGraph2([idle], transitions=(AnimationTransition2("missing", "idle"),))
    with pytest.raises(KeyError):
        AnimationGraph2([idle], transitions=(AnimationTransition2("idle", "missing"),))
    with pytest.raises(KeyError):
        AnimationGraph2(
            [idle],
            transitions=(
                AnimationTransition2(
                    "idle",
                    "idle",
                    (AnimationCondition("missing", ConditionOperator.EQ, 1),),
                ),
            ),
        )


def test_diagnostics_and_state_fingerprint_are_reproducible() -> None:
    graph = AnimationGraph2(
        [
            AnimationState2("idle", clip("idle", 0.0, 1.0)),
            AnimationState2("run", clip("run", 10.0, 20.0)),
        ],
        parameters=(AnimationParameter("speed", ParameterKind.FLOAT),),
        transitions=(
            AnimationTransition2(
                "idle",
                "run",
                (AnimationCondition("speed", ConditionOperator.GT, 0.0),),
                duration=0.25,
            ),
        ),
    )
    first = AnimationGraphPlayer(graph)
    second = AnimationGraphPlayer(graph)
    for player in (first, second):
        player.set_parameter("speed", 2.0)
        player.update(0.1)
        player.update(0.1)
    assert first.state_fingerprint() == second.state_fingerprint()
    diagnostics = first.diagnostics()
    assert diagnostics.current_state == "idle"
    assert diagnostics.next_state == "run"
    assert diagnostics.transition_progress == pytest.approx(0.4)
    assert diagnostics.parameters["speed"] == pytest.approx(2.0)


def test_runtime_rejects_nonfinite_and_negative_time_inputs() -> None:
    with pytest.raises(ValueError):
        AnimationKeyframe(float("nan"), 0.0)
    animation = clip("idle", 0.0, 1.0)
    with pytest.raises(ValueError):
        animation.sample(-1.0)
    player = AnimationGraphPlayer(AnimationGraph2([AnimationState2("idle", animation)]))
    with pytest.raises(ValueError):
        player.update(-0.1)
    with pytest.raises(ValueError):
        player.update(float("inf"))
