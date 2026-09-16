from __future__ import annotations

import time

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


def make_clip(name: str, base: float) -> AnimationClip:
    return AnimationClip(
        name,
        1.0,
        tuple(
            AnimationTrack(
                f"channel_{index}",
                (
                    AnimationKeyframe(0.0, base + index),
                    AnimationKeyframe(1.0, base + index + 1.0),
                ),
            )
            for index in range(8)
        ),
    )


def main() -> None:
    graph = AnimationGraph2(
        [
            AnimationState2("idle", make_clip("idle", 0.0)),
            AnimationState2("run", make_clip("run", 10.0)),
        ],
        parameters=(AnimationParameter("speed", ParameterKind.FLOAT),),
        transitions=(
            AnimationTransition2(
                "idle",
                "run",
                (AnimationCondition("speed", ConditionOperator.GT, 0.1),),
                duration=0.08,
            ),
            AnimationTransition2(
                "run",
                "idle",
                (AnimationCondition("speed", ConditionOperator.LE, 0.1),),
                duration=0.08,
            ),
        ),
    )
    player = AnimationGraphPlayer(graph)
    started = time.perf_counter()
    for index in range(5_000):
        if index % 125 == 0:
            player.set_parameter("speed", 1.0 if (index // 125) % 2 == 0 else 0.0)
        player.update(1.0 / 120.0)
        if index % 50 == 0:
            player.state_fingerprint()
    elapsed = time.perf_counter() - started
    budget = 2.0
    print(f"5,000 animation graph updates: {elapsed:.6f}s (budget {budget:.1f}s)")
    print(f"transitions: {player.transitions_taken}")
    if elapsed > budget:
        raise SystemExit(
            f"animation graph workload exceeded budget: {elapsed:.6f}s > {budget:.1f}s"
        )


if __name__ == "__main__":
    main()
