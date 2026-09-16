# Animation Graphs 2.0 — SwirEngine 1.5

SwirEngine 1.5 adds an opt-in creator animation graph runtime in `swirengine.animation15`.
It builds on the released 1.x animation interpolation behavior without changing stable root imports
or the established `Tween`, `AnimationTimeline`, `StateMachine` and `AnimationSystem` APIs.

## Goals

Animation Graphs 2.0 provides a deterministic, renderer-independent layer for reusable authored
animation logic:

- reusable named clips built from property-binding tracks and keyframes;
- linear and step sampling with explicit looping or clamping;
- typed graph parameters (`bool`, `float`, `int`, `trigger`);
- prioritized state transitions, wildcard transitions and normalized exit-time gates;
- deterministic trigger consumption;
- timed cross-fades between source and target poses;
- generic pose application to nested object or mapping paths;
- portable diagnostics and SHA-256 state/pose fingerprints for CI, replay and server tooling.

The runtime is deliberately headless. It produces animation poses as binding/value mappings, so the
same graph logic can drive scene objects, skeletal adapters, UI properties or creator tooling without
requiring an OpenGL context.

## Clips and tracks

```python
from swirengine.animation15 import AnimationClip, AnimationKeyframe, AnimationTrack

idle = AnimationClip(
    "idle",
    1.0,
    (
        AnimationTrack(
            "transform.scale",
            (
                AnimationKeyframe(0.0, [1.0, 1.0, 1.0]),
                AnimationKeyframe(1.0, [1.02, 1.02, 1.02]),
            ),
        ),
    ),
)
```

Tracks require strictly increasing keyframe times. Keyframes may end before the clip duration, in
which case the last value is held. No keyframe may exceed the clip duration. Linear tracks reuse the
stable 1.x interpolation semantics for numbers, tuples, lists and compatible custom values. Step
tracks hold the previous keyframe value until the next keyframe is reached.

`AnimationClip.sample(time, loop=False)` clamps at the clip end. Passing `loop=True` wraps the sample
time by the clip duration.

## Parameters and transitions

```python
from swirengine.animation15 import (
    AnimationCondition,
    AnimationGraph2,
    AnimationParameter,
    AnimationState2,
    AnimationTransition2,
    ConditionOperator,
    ParameterKind,
)

graph = AnimationGraph2(
    [
        AnimationState2("idle", idle),
        AnimationState2("run", run_clip),
    ],
    parameters=(AnimationParameter("speed", ParameterKind.FLOAT),),
    transitions=(
        AnimationTransition2(
            "idle",
            "run",
            (AnimationCondition("speed", ConditionOperator.GT, 0.1),),
            duration=0.2,
            priority=10,
        ),
    ),
)
```

Transitions are evaluated deterministically by descending priority and then declaration order.
`"*"` is accepted as a wildcard source. By default a transition targeting the already-current state
is ignored; `allow_self=True` opts into an explicit self-transition.

`exit_time` is a normalized source-state threshold from `0.0` to `1.0`. Once the source state's
unbounded runtime reaches that threshold, the transition remains eligible when its conditions match.
This avoids losing a transition merely because a looping clip wrapped between two updates.

Trigger parameters default to `False`, can be raised with `player.trigger(name)`, and are consumed
only by the transition that actually wins selection when `consume_triggers=True`.

## Cross-fade contract

When a transition has `duration > 0`, the source and target states both continue advancing while the
blend is active. Shared bindings are interpolated using the stable 1.x interpolation contract.
Target-only bindings are available immediately, while source-only bindings are retained until the
blend completes and then disappear from the target pose. Zero-duration transitions switch states
immediately and begin the target at local time zero.

This contract is intentionally data-oriented. Animation Graphs 2.0 does not assume a skeletal mesh
format; future adapters can translate pose bindings into bone transforms without changing the graph
runtime.

## Headless player and diagnostics

```python
from swirengine.animation15 import AnimationGraphPlayer

player = AnimationGraphPlayer(graph)
player.set_parameter("speed", 3.0)
pose = player.update(1 / 60)
pose.apply(actor)
print(player.diagnostics())
print(player.state_fingerprint())
```

`AnimationGraphDiagnostics` reports the current and next state, source runtime, normalized time,
transition progress, transition count, typed parameter snapshot and current pose fingerprint.
`state_fingerprint()` hashes canonical portable diagnostics, making equivalent headless runs easy to
compare in replay tests and CI.

## Compatibility

Animation Graphs 2.0 is additive and opt-in through `swirengine.animation15`. It does not modify
`swirengine.__init__`, `swirengine.animation_runtime`, stable 1.x root imports, or existing tween and
timeline behavior. The published package remains version 1.4.0 until all ten SwirEngine 1.5
milestones and the final release gate are complete.

## Validation

The dedicated validation gate targets Python 3.10, 3.13 and 3.14 and covers:

- linear and step clip sampling;
- clamp/loop behavior and nested pose application;
- deterministic pose blending and fingerprints;
- typed bool/float/int/trigger parameters;
- transition priority, wildcard transitions and trigger consumption;
- timed cross-fades and zero-duration switches;
- exit-time gating;
- invalid graph/transition/parameter contracts;
- reproducible headless diagnostics;
- non-finite and negative-time rejection;
- a 5,000-update graph workload with eight sampled channels;
- the runnable headless Animation Graphs 2.0 demo.

Run locally:

```bash
pytest tests/test_animation_graphs_2_1_5.py
ruff check src/swirengine/animation15.py tests/test_animation_graphs_2_1_5.py \
  tools/benchmark_animation_graphs_2_1_5.py examples/demo_animation_graphs_2_1_5.py
python -m compileall -q src/swirengine/animation15.py tests/test_animation_graphs_2_1_5.py \
  tools/benchmark_animation_graphs_2_1_5.py examples/demo_animation_graphs_2_1_5.py
python tools/benchmark_animation_graphs_2_1_5.py
python examples/demo_animation_graphs_2_1_5.py
```
