# Deterministic Simulation & Replay — SwirEngine 1.5

SwirEngine 1.5 starts with an opt-in deterministic simulation and replay layer. It is intentionally additive: the stable 1.x root API and the released 1.4 behavior remain unchanged.

## Goals

The subsystem provides four creator-facing building blocks:

- `FixedStepClock` converts variable host-frame time into bounded fixed simulation ticks.
- `ReplayRecorder` captures portable input payloads, optional state fingerprints and periodic checkpoints.
- `ReplayRecording` is a versioned, canonical JSON format for test fixtures, bug reports and replay tooling.
- `ReplayPlayer` replays creator-owned simulation callbacks, verifies state fingerprints and can seek from checkpoints.

The engine does **not** claim that arbitrary Python code becomes deterministic automatically. Determinism still depends on creator code using deterministic inputs, explicit random seeds and stable simulation rules. The replay layer makes that contract observable and testable.

## Quick start

```python
from swirengine.simulation15 import ReplayPlayer, ReplayRecorder

state = {"x": 0}
recorder = ReplayRecorder(step_seconds=1 / 60, checkpoint_interval=120)
recorder.add_checkpoint(0, state)

for tick, movement in enumerate((1, 1, -1, 2), start=1):
    state["x"] += movement
    recorder.record(tick, {"movement": movement}, state=state)

recording = recorder.build(metadata={"level": "demo"})
replayed = {"x": 0}


def step(_tick: int, _dt: float, payload: dict[str, object]) -> None:
    replayed["x"] += int(payload["movement"])


report = ReplayPlayer(
    recording,
    step,
    state_provider=lambda: replayed,
).play()

assert report.verified_frames == 4
assert replayed == state
```

## Fixed-step clock

`FixedStepClock` accumulates non-negative wall-clock deltas and emits `SimulationTick` records at a fixed `step_seconds`. `max_steps_per_advance` is a spiral-of-death guard: excess whole steps are dropped and counted in `dropped_steps`, while the fractional remainder is retained for interpolation through `alpha`.

This clock does not sleep, schedule threads or read the system clock. The host owns timing and passes elapsed seconds explicitly.

## Portable replay data

Replay inputs, metadata, checkpoints and states accept:

- `None`
- booleans
- strings
- integers
- finite floats
- lists/tuples of portable values
- mappings with string keys

Non-finite floats, object instances and non-string mapping keys are rejected. `-0.0` is canonicalized to `0.0`. Canonical JSON uses sorted mapping keys and compact separators.

`state_fingerprint()` computes a SHA-256 digest of the canonical state representation. It is a divergence detector, not a security boundary.

## Recording and verification

When `state=` is supplied to `ReplayRecorder.record()`, the frame stores a state fingerprint. A player with `state_provider=` recalculates the fingerprint after each step and raises `ReplayDivergenceError` on the first mismatch.

Set `verify=False` only when deliberately consuming a recording without state verification.

`max_frames` creates a bounded rolling capture suitable for recent-history diagnostics. Checkpoints that can no longer restore the retained frame window are pruned.

## Checkpoints and seek

Call `add_checkpoint(0, initial_state)` to make the initial state seekable. Periodic checkpoints can be created automatically with `checkpoint_interval=N` whenever `record(..., state=...)` is used.

`ReplayPlayer.seek(tick)` requires `state_restorer=`. It restores the nearest checkpoint at or before the requested tick and replays forward to the target. A checkpoint represents the state **after** its tick.

## Versioning

The initial portable format is:

- format: `swirengine.replay`
- version: `1`

Unknown formats and versions are rejected instead of being guessed. Future migrations must be explicit so old bug captures never silently change meaning.

## Validation

The dedicated validation gate covers:

- Python 3.10, 3.13 and 3.14
- fixed-step accumulation and catch-up bounds
- canonical hashing and invalid-data rejection
- JSON round-trips and format/version gates
- bounded recording and checkpoint pruning
- exact replay verification and first-divergence reporting
- checkpoint seeking
- a 5,000-frame record/serialize/parse/replay workload
- runnable deterministic replay demo

Run locally:

```bash
pytest tests/test_deterministic_replay_1_5.py
ruff check src/swirengine/simulation15.py tests/test_deterministic_replay_1_5.py tools/benchmark_deterministic_replay_1_5.py examples/demo_deterministic_replay_1_5.py
python -m compileall -q src/swirengine/simulation15.py tests/test_deterministic_replay_1_5.py tools/benchmark_deterministic_replay_1_5.py examples/demo_deterministic_replay_1_5.py
python tools/benchmark_deterministic_replay_1_5.py
python examples/demo_deterministic_replay_1_5.py
```
