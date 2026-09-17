# Batched Upload, Staging & Texture Residency — SwirEngine 1.8

SwirEngine 1.8 adds an opt-in metadata planning layer for bounded renderer uploads and deterministic
texture/resource residency. The layer lives in `swirengine.upload_residency18`; it does not replace
or alter stable 1.x renderer APIs.

The module deliberately does **not** own image bytes, OpenGL objects, command buffers or backend
threads. Creator/backend code keeps those responsibilities. SwirEngine provides deterministic queue,
staging, back-pressure and residency decisions that can be tested headlessly before a renderer
executes the actual upload.

## Upload requests

`UploadRequest` contains portable metadata only:

- `asset_id` — stable creator asset identifier;
- `revision` — monotonically increasing content revision chosen by the creator/asset pipeline;
- `size_bytes` — declared upload/residency cost;
- `priority` — creator-owned scheduling/residency priority;
- `kind` — descriptive resource class, defaulting to `texture`.

No creator payload or backend object is stored in portable diagnostics.

## Bounded upload queue

`BoundedUploadQueue` has independent hard limits for:

- total outstanding request count;
- total outstanding declared bytes;
- staged bytes;
- bytes per batch;
- requests per batch.

Accepted requests are staged in deterministic order: higher creator priority first, then original
enqueue order, then asset id. Requests that do not fit the current batch may be skipped so smaller
work can progress without violating the byte budget.

Back-pressure is explicit through `UploadResidencyError` codes such as
`outstanding-requests`, `outstanding-bytes`, `request-too-large` and `staging-backpressure`.
Rejected requests leave queue state unchanged.

## Duplicate and revision handling

For the same asset id:

- an equal or older pending/staged revision is suppressed;
- a newer pending revision replaces an older **pending** revision atomically;
- a newer revision may wait while an older revision is already staged;
- aborting that older staged batch will not resurrect it over the newer pending revision.

Completing a batch releases its staging/outstanding budget. Aborting a batch restores eligible work
with its original deterministic sequence. A stale/already-finished batch id fails explicitly.

## Texture/resource residency

`TextureResidencyManager` tracks portable metadata for resident uploaded resources. It has hard
resource-count and byte budgets and never stores backend objects.

Admission uses deterministic eviction order:

1. lowest creator priority;
2. least-recently-used sequence;
3. asset id.

Pinned entries are not eviction candidates. An incoming resource is not allowed to evict a resident
with a strictly higher priority. If the required capacity cannot be made available under those
rules, admission fails atomically with `residency-pressure`.

A newer revision of an already-resident asset replaces the old revision without artificially
consuming a second resource slot. Equal/older revisions are suppressed. `touch()` updates only the
LRU tie-break, while `set_pinned()` and explicit `evict()` give creators direct lifecycle control.

## Typical renderer integration

```python
from swirengine.upload_residency18 import (
    BoundedUploadQueue,
    TextureResidencyManager,
    UploadRequest,
)

queue = BoundedUploadQueue(max_staging_bytes=64 * 1024 * 1024)
residency = TextureResidencyManager(max_resources=2048, max_bytes=1024 * 1024 * 1024)

queue.enqueue(UploadRequest("terrain/albedo", 4, 8 * 1024 * 1024, priority=20))
batch = queue.stage_batch()
if batch is not None:
    # backend_upload(batch.requests, creator_payload_store)
    for request in batch.requests:
        residency.admit(request)
    queue.complete_batch(batch.batch_id)
```

If backend upload fails before completion, call `abort_batch(batch.batch_id)` so staged requests are
made eligible for a later retry without violating queue accounting.

## Diagnostics

Both queue and residency diagnostics are payload-free numeric contracts suitable for headless tests,
servers and creator tooling. They expose queue/staging/outstanding pressure, peaks, duplicate
suppression, supersession, completion/abort counters, resident resources/bytes, evictions, touches
and pressure failures.

`TextureResidencyManager.snapshot()` returns immutable portable resident metadata in stable asset-id
order. It never exposes renderer objects.

## Verification contract

The dedicated `Upload Residency 1.8` workflow validates the new surface on Python 3.10, 3.13 and
3.14 together with the verified 1.8 Render Graph / transient-resource layers and stable 1.4 renderer
regressions. It runs focused tests, strict Ruff, compile checks, a creator demo and a deterministic
Python 3.13 workload.

The workload drives 8,000 logical enqueue attempts through bounded batches across 256 logical assets,
then validates the residency ceilings and deterministic eviction behavior under a generous 5-second
CI budget. This is a scheduling/planning regression gate, not an FPS or GPU-throughput claim.

Milestone completion additionally requires the repository-wide compatibility/regression workflows to
remain green on the exact final PR head.

SwirEngine 1.8 remains a source-only checkpoint. **Release/PyPI: frozen until SwirEngine 2.0.**
