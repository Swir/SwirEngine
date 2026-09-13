from dataclasses import dataclass, field

import pytest

from swirengine.animation_runtime import (
    AnimationSystem,
    AnimationTimeline,
    Ease,
    State,
    StateMachine,
    Tween,
    TweenSequence,
    ease_value,
    interpolate,
)


@dataclass
class Actor:
    x: float = 0.0
    alpha: float = 1.0
    transform: dict[str, object] = field(default_factory=lambda: {"position": [0.0, 0.0, 0.0]})


def test_easing_and_interpolation_are_deterministic() -> None:
    assert ease_value(Ease.LINEAR, 0.25) == pytest.approx(0.25)
    assert ease_value(Ease.IN_QUAD, 0.5) == pytest.approx(0.25)
    assert ease_value(Ease.OUT_QUAD, 0.5) == pytest.approx(0.75)
    assert ease_value(Ease.IN_OUT_QUAD, 0.25) == pytest.approx(0.125)
    assert interpolate((0.0, 10.0), (10.0, 30.0), 0.5) == pytest.approx((5.0, 20.0))
    assert interpolate([0.0, 2.0], [10.0, 6.0], 0.25) == pytest.approx([2.5, 3.0])


def test_tween_supports_nested_paths_delay_and_completion() -> None:
    actor = Actor()
    completed: list[str] = []
    tween = Tween(
        actor,
        "transform.position",
        [10.0, 20.0, 30.0],
        duration=2.0,
        delay=0.5,
        ease=Ease.LINEAR,
        on_complete=lambda _: completed.append("done"),
    )

    assert not tween.update(0.25)
    assert actor.transform["position"] == [0.0, 0.0, 0.0]
    tween.update(1.25)
    assert actor.transform["position"] == pytest.approx([5.0, 10.0, 15.0])
    assert tween.update(1.0)
    assert actor.transform["position"] == pytest.approx([10.0, 20.0, 30.0])
    assert completed == ["done"]
    assert tween.update(1.0)
    assert completed == ["done"]


def test_tween_repeat_yoyo_returns_to_start() -> None:
    actor = Actor()
    tween = Tween(actor, "x", 10.0, duration=1.0, repeat=1, yoyo=True)
    tween.update(0.5)
    assert actor.x == pytest.approx(5.0)
    tween.update(0.5)
    assert actor.x == pytest.approx(10.0)
    tween.update(0.5)
    assert actor.x == pytest.approx(5.0)
    assert tween.update(0.5)
    assert actor.x == pytest.approx(0.0)


def test_sequence_runs_tweens_in_order() -> None:
    actor = Actor()
    sequence = TweenSequence(
        [
            Tween(actor, "x", 10.0, duration=1.0),
            Tween(actor, "alpha", 0.0, duration=1.0),
        ]
    )
    assert not sequence.update(1.0)
    assert actor.x == pytest.approx(10.0)
    assert actor.alpha == pytest.approx(1.0)
    assert sequence.update(1.0)
    assert actor.alpha == pytest.approx(0.0)
    assert not sequence.playing


def test_timeline_updates_parallel_tracks_and_markers() -> None:
    actor = Actor()
    markers: list[str] = []
    timeline = AnimationTimeline(on_marker=lambda marker: markers.append(marker.name))
    timeline.add(Tween(actor, "x", 20.0, duration=2.0, ease=Ease.LINEAR))
    timeline.add(Tween(actor, "alpha", 0.0, duration=1.0, ease=Ease.LINEAR))
    timeline.add_marker(0.5, "footstep")
    timeline.add_marker(1.5, "impact")

    assert not timeline.update(0.5)
    assert actor.x == pytest.approx(5.0)
    assert actor.alpha == pytest.approx(0.5)
    assert markers == ["footstep"]
    timeline.update(1.0)
    assert markers == ["footstep", "impact"]
    assert timeline.update(0.5)
    assert actor.x == pytest.approx(20.0)
    assert actor.alpha == pytest.approx(0.0)


def test_timeline_seek_reconstructs_property_state_without_marker_callbacks() -> None:
    actor = Actor()
    markers: list[str] = []
    timeline = AnimationTimeline(on_marker=lambda marker: markers.append(marker.name))
    timeline.add(Tween(actor, "x", 40.0, duration=4.0))
    timeline.add_marker(1.0, "one")
    timeline.seek(2.0)
    assert actor.x == pytest.approx(20.0)
    assert markers == []


def test_state_machine_runs_callbacks_and_priority_transitions() -> None:
    events: list[tuple[str, object]] = []
    context = {"grounded": True, "speed": 0.0, "dead": False}
    machine = StateMachine(
        [
            State("idle", on_enter=lambda previous: events.append(("idle_enter", previous))),
            State("run", on_update=lambda dt: events.append(("run_update", dt))),
            State("dead", on_enter=lambda previous: events.append(("dead_enter", previous))),
        ],
        initial="idle",
    )
    machine.add_transition("*", "dead", lambda: context["dead"], priority=100)
    machine.add_transition("idle", "run", lambda: context["speed"] > 0.1, priority=10)

    context["speed"] = 2.0
    assert machine.update(0.016) == "run"
    machine.update(0.25)
    assert ("run_update", 0.25) in events
    context["dead"] = True
    assert machine.update(0.016) == "dead"
    assert ("dead_enter", "run") in events
    assert machine.time_in_state == 0.0


def test_animation_system_updates_mixed_runtime_objects() -> None:
    actor = Actor()
    machine = StateMachine([State("idle")], initial="idle")
    timeline = AnimationTimeline([Tween(actor, "x", 10.0, duration=1.0)])
    sequence = TweenSequence([Tween(actor, "alpha", 0.0, duration=1.0)])
    system = AnimationSystem()
    assert system.add(timeline) is timeline
    assert system.add(sequence) is sequence
    assert system.add(machine) is machine
    system.update(0.5)
    assert actor.x == pytest.approx(5.0)
    assert actor.alpha == pytest.approx(0.5)
    system.update(0.5)
    system.prune_finished()
    assert system.timelines == []
    assert system.sequences == []
    assert system.state_machines == [machine]


def test_animation_runtime_rejects_invalid_time_inputs() -> None:
    actor = Actor()
    with pytest.raises(ValueError):
        Tween(actor, "x", 1.0, duration=-1.0)
    tween = Tween(actor, "x", 1.0, duration=1.0)
    with pytest.raises(ValueError):
        tween.update(-0.1)
    machine = StateMachine([State("idle")], initial="idle")
    with pytest.raises(ValueError):
        machine.update(-0.1)
