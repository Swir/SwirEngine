from __future__ import annotations

from swirengine.animation15 import (
    AnimationClip,
    AnimationCondition,
    AnimationGraph2,
    AnimationGraphPlayer,
    AnimationKeyframe,
    AnimationParameter,
    AnimationState2,
    AnimationTrack,
    AnimationTransition2,
    ConditionOperator,
    ParameterKind,
)


def motion_clip(name: str, start: float, end: float) -> AnimationClip:
    return AnimationClip(
        name,
        1.0,
        (
            AnimationTrack(
                "body.lean",
                (AnimationKeyframe(0.0, start), AnimationKeyframe(1.0, end)),
            ),
        ),
    )


def main() -> None:
    graph = AnimationGraph2(
        [
            AnimationState2("idle", motion_clip("idle", 0.0, 0.05)),
            AnimationState2("run", motion_clip("run", 0.2, 0.5)),
            AnimationState2("attack", motion_clip("attack", 1.0, 0.0), loop=False),
        ],
        parameters=(
            AnimationParameter("speed", ParameterKind.FLOAT),
            AnimationParameter("attack", ParameterKind.TRIGGER),
        ),
        transitions=(
            AnimationTransition2(
                "*",
                "attack",
                (AnimationCondition("attack", ConditionOperator.TRIGGER),),
                duration=0.1,
                priority=100,
            ),
            AnimationTransition2(
                "idle",
                "run",
                (AnimationCondition("speed", ConditionOperator.GT, 0.1),),
                duration=0.2,
                priority=10,
            ),
            AnimationTransition2(
                "run",
                "idle",
                (AnimationCondition("speed", ConditionOperator.LE, 0.1),),
                duration=0.2,
                priority=10,
            ),
            AnimationTransition2("attack", "idle", exit_time=1.0),
        ),
    )
    player = AnimationGraphPlayer(graph)
    player.set_parameter("speed", 4.0)
    for _ in range(8):
        player.update(1.0 / 60.0)
    player.trigger("attack")
    for _ in range(70):
        player.update(1.0 / 60.0)

    diagnostics = player.diagnostics()
    print("SwirEngine 1.5 Animation Graphs 2.0 demo")
    print(f"state: {diagnostics.current_state}")
    print(f"next state: {diagnostics.next_state}")
    print(f"transitions: {diagnostics.transitions_taken}")
    print(f"normalized time: {diagnostics.normalized_time:.3f}")
    print(f"pose fingerprint: {diagnostics.pose_fingerprint}")
    print(f"runtime fingerprint: {player.state_fingerprint()}")

    assert diagnostics.transitions_taken >= 2
    assert len(player.state_fingerprint()) == 64


if __name__ == "__main__":
    main()
