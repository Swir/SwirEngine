# Prediction & Reconciliation 2.0 (SwirEngine 1.6)

SwirEngine 1.6 adds an opt-in prediction/reconciliation timeline in `swirengine.prediction16`. It builds on the stable `PredictionCommand` model from SwirEngine 1.4 without changing `ClientPredictor` or existing root-package behavior.

## Goals

Prediction & Reconciliation 2.0 makes client prediction safer under packet loss and packet reordering while keeping the simulation contract deterministic:

- every authoritative correction carries both an acknowledged command sequence and the replication tick that produced it;
- out-of-order or duplicate authoritative ticks are ignored instead of rolling simulation truth backward;
- prediction is bounded by a configurable tick window ahead of the newest authoritative state;
- pending commands and reconciliation replay both have independent hard budgets;
- replay-budget failures are atomic: no state, acknowledgement or authoritative tick is partially advanced;
- corrected simulation truth is applied immediately;
- presentation smoothing is exposed as a separate `CorrectionTransition`, so visual easing cannot delay or contaminate authoritative simulation state;
- corrections serialize through the existing stable `NetworkPacket` transport.

## Basic flow

```python
from swirengine.multiplayer14 import PredictionCommand
from swirengine.prediction16 import PredictionCorrection, PredictionTimeline


def simulate(state, command):
    state["x"] = state.get("x", 0.0) + command.payload.get("dx", 0.0)
    return state


timeline = PredictionTimeline(
    {"x": 0.0},
    simulate,
    max_prediction_ticks=8,
    max_replay_commands=64,
)

timeline.predict(PredictionCommand(sequence=1, tick=1, payload={"dx": 1.0}))
timeline.predict(PredictionCommand(sequence=2, tick=2, payload={"dx": 1.0}))

result = timeline.reconcile(
    PredictionCorrection(
        acknowledged_sequence=1,
        replication_tick=4,
        authoritative_state={"x": 0.8},
    )
)

# Command 2 is replayed deterministically over authoritative truth.
assert result.replayed_commands == 1
assert timeline.last_authoritative_tick == 4
```

## Replication-tick ordering

`PredictionCorrection.replication_tick` is the ordering key for authoritative state. A correction whose tick is less than or equal to the latest applied authoritative tick is treated as stale and ignored. This makes duplicate delivery and packet reordering safe by default.

A newer authoritative tick may acknowledge the same or a higher command sequence. It may not regress below the last accepted acknowledgement. A server also cannot acknowledge a sequence the client has never predicted.

These checks make contradictory network state fail loudly instead of silently discarding or replaying the wrong input history.

## Prediction window

`max_prediction_ticks` limits how far a command may run ahead of `last_authoritative_tick`:

```python
timeline = PredictionTimeline(
    initial_state,
    simulate,
    max_prediction_ticks=6,
)
```

Commands behind the authoritative timeline or beyond the configured future window are rejected before state is simulated. Rejections leave the sequence counter, pending queue and simulation state unchanged.

This is separate from `max_pending`, which limits the number of unacknowledged commands retained in memory.

## Deterministic replay budget

`max_replay_commands` limits the number of pending commands that one reconciliation may replay. If a correction would require more work, `ReplayBudgetExceeded` is raised before any timeline state changes:

```python
from swirengine.prediction16 import ReplayBudgetExceeded

try:
    timeline.reconcile(correction)
except ReplayBudgetExceeded:
    # Request a creator-defined full prediction reset/resync policy.
    ...
```

The engine intentionally does not guess a destructive recovery policy. Games can choose whether to request a fresh authoritative state, temporarily disable local prediction, or reset a controlled gameplay subsystem.

## Correction smoothing without changing truth

When reconciliation changes the currently predicted state, the result contains a `CorrectionTransition`:

```python
result = timeline.reconcile(correction)

if result.transition:
    display_state = result.transition.sample(0.35)
```

`timeline.state` already contains corrected simulation truth at this point. Sampling the transition only produces presentation state. The built-in sampler linearly blends numeric values and keeps nonnumeric values on the previous side until the transition completes.

Creators can supply a custom presentation-only blend hook:

```python
def ease(previous, corrected, alpha):
    eased = alpha * alpha * (3.0 - 2.0 * alpha)
    return {"x": previous["x"] + (corrected["x"] - previous["x"]) * eased}

display_state = result.transition.sample(0.5, blend=ease)
```

The hook receives portable state copies and must return a portable mapping. It never mutates `PredictionTimeline.state`.

## Packet bridge

`PredictionCorrection.to_packet()` creates a stable `NetworkPacket` with kind:

```text
swir.prediction16.correction
```

`PredictionCorrection.from_packet()` reverses the operation. This keeps the 1.6 feature transport-independent and compatible with existing TCP/gameplay-session framing as well as custom transports that carry `NetworkPacket` payloads.

## Diagnostics

`timeline.diagnostics()` returns deterministic integer counters for:

- predicted commands;
- successful reconciliations;
- stale corrections;
- corrected reconciliations;
- replayed commands;
- replay-budget rejections;
- prediction-window rejections;
- pending-history overflow rejections;
- peak pending commands.

No wall-clock timing is used in the correctness counters.

## Compatibility boundary

Prediction & Reconciliation 2.0 is additive:

- new API: `swirengine.prediction16`;
- stable command type reused: `swirengine.multiplayer14.PredictionCommand`;
- stable `ClientPredictor` remains unchanged and continues to be covered by regression tests;
- no root-package import is added in this milestone;
- no transport framing or stable multiplayer packet kind is modified.
