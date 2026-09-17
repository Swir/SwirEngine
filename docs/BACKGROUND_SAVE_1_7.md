# Background Save & Serialization I/O — SwirEngine 1.7

`swirengine.background_save17` is an additive, opt-in save pipeline for games that need disk I/O away from the frame-owning thread without weakening the released Save/Profile 2.0 recovery contract.

## Ownership model

`BackgroundSavePipeline.submit(...)` captures creator-owned state immediately on the pipeline's owning thread. The capture is normalized to portable JSON and stored as an immutable canonical string plus a SHA-256 fingerprint before any worker is admitted. A game can therefore continue mutating its live dictionaries, lists and component snapshots after submission without changing the save already in flight.

The worker receives no live game object, `Scene`, renderer, window or creator mapping. It only receives the prepared JSON snapshot and a `SaveSlotStore2`.

## Atomic write and verification

Workers write through the existing `SaveSlotStore2.save(...)` API rather than duplicating its file format. That preserves:

- versioned Save/Profile 2.0 envelopes;
- SHA-256 integrity records;
- monotonically increasing slot revisions;
- validated last-known-good `.bak` recovery;
- atomic temporary-file write, fsync and `os.replace(...)` promotion;
- existing migration/default handling on load.

After promotion, the worker immediately loads the primary through `SaveSlotStore2.load()` and verifies revision, metadata and every requested data key before reporting success.

## Cancellation boundary

Cancellation is cooperative only while a request is queued or preparing its immutable worker-side payload. Immediately before `SaveSlotStore2.save(...)` starts, the request enters `COMMITTING`.

Once `COMMITTING` is visible, `cancel(...)` returns `False` and does not set the underlying job cancellation token. This is deliberate: after atomic promotion has started, the pipeline must finish or report a write/verification failure rather than claim that an already-committed save was cancelled.

## Slot serialization

Only one unfinished background request may target a canonical save path at a time. A second request for the same slot is rejected instead of racing revision discovery, backup rotation or promotion. Independent slots can run concurrently up to the configured worker and request budgets.

## Creator example

```python
from swirengine.background_save17 import BackgroundSavePipeline
from swirengine.storage15 import ProfileSaveManager2

manager = ProfileSaveManager2("save-data", "player-1")
live_state = {"hp": 100, "inventory": ["key"]}

with BackgroundSavePipeline(max_workers=2) as saves:
    saves.submit_profile(
        "checkpoint",
        manager,
        "campaign",
        lambda: live_state,
        metadata={"reason": "checkpoint"},
    )

    # Safe: the submitted save already owns an immutable snapshot.
    live_state["hp"] = 50

    outcome = saves.run_until_idle()[0]
    assert outcome.successful
```

For frame-based games, call `poll(max_items=...)` from the owning thread instead of `run_until_idle()`. Polling transfers only terminal outcomes; disk I/O and verification remain on workers.

## Diagnostics and limits

`BackgroundSaveDiagnostics` exposes counts and budgets only. It intentionally does not expose save payloads. The pipeline tracks queued/writing/committing/terminal requests, active slot count, accepted/rejected work, cancellation requests/refusals, snapshot byte volume and verified writes.

`max_workers` bounds worker concurrency and `max_requests` bounds unfinished retained work. Invalid/non-portable snapshots fail synchronously before a worker or target file is created.

## Compatibility

This module does not replace or modify stable `SaveStore`, `ProfileStore`, `SaveSlotStore2` or `ProfileSaveManager2` behavior. It composes the public Save/Profile 2.0 APIs and remains opt-in. Published SwirEngine 1.5.0 metadata is unchanged.

SwirEngine 1.7 remains a source-development checkpoint. **Release/PyPI remain frozen until SwirEngine 2.0.**
