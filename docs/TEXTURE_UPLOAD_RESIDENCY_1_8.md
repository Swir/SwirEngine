# Texture Upload, Staging & Residency 1.8

SwirEngine 1.8 adds an opt-in, renderer-independent texture upload queue in
`swirengine.render_uploads18`. It does not replace stable 1.x texture APIs and does not perform GPU
work by itself. Creators or renderer backends provide explicit upload and optional eviction callbacks.

## Goals

The queue is designed for dynamic textures, sprite atlases, generated UI surfaces, streaming texture
content, and other workloads where unbounded uploads can destabilize frame time or memory use. The
contract provides:

- immutable payload snapshots at enqueue time;
- full-texture and rectangular layer-region updates;
- strict queue count/byte limits and per-flush upload/byte budgets;
- deterministic FIFO submission and explicit deferral rather than silent work loss;
- descriptor-aware SHA-256 duplicate suppression based only on content that was successfully submitted;
- deterministic logical texture residency with creator priorities, last-use ordering and pinning;
- bounded resident texture/byte limits with explicit backend eviction callbacks;
- stable failure codes, portable numeric diagnostics and deterministic state fingerprints.

The queue deliberately does not infer texel byte size from format strings. Compressed, packed and
backend-specific texture formats make such assumptions unsafe. Region geometry is validated against
the declared texture dimensions/layers, while payload interpretation remains the backend's job.

## Basic use

```python
from swirengine.render_resources18 import RenderResourceDescriptor
from swirengine.render_uploads18 import TextureUploadQueue, TextureUploadRegion


def submit(upload):
    # Backend-specific copy/upload code belongs here.
    print(upload.texture_id, upload.region, upload.byte_count)


def evict(texture_id):
    # Release the backend texture or residency allocation here.
    print("evict", texture_id)


queue = TextureUploadQueue(
    submit=submit,
    evict=evict,
    max_pending_uploads=128,
    max_pending_bytes=32 * 1024 * 1024,
    max_uploads_per_flush=32,
    max_bytes_per_flush=8 * 1024 * 1024,
    max_resident_textures=512,
    max_resident_bytes=256 * 1024 * 1024,
)

atlas = RenderResourceDescriptor(
    "texture",
    "rgba8",
    2048,
    2048,
    usage="sampled",
    size_bytes=2048 * 2048 * 4,
)

queue.enqueue(
    "ui-atlas",
    atlas,
    tile_bytes,
    region=TextureUploadRegion(128, 256, 64, 64),
    priority=5,
)
queue.flush()
```

`bytearray` and `memoryview` inputs are copied to immutable `bytes` when they enter the queue. The
queue checks the bytes-like object's reported size against pending/per-flush limits before taking that
copy, so an already-over-budget mutable upload is rejected without first allocating a second staging
buffer. A caller cannot mutate already-queued GPU work accidentally.

## Upload budgets and back-pressure

Three independent limits protect staging work:

1. `max_pending_uploads` bounds queued request count.
2. `max_pending_bytes` bounds queued payload memory.
3. `max_uploads_per_flush` and `max_bytes_per_flush` bound work released to the backend per flush.

A single request larger than `max_bytes_per_flush` is rejected with `upload-too-large` instead of
remaining permanently stuck at the head of the queue. Pending count/byte pressure uses `queue-full`
or `queue-bytes-full`. Work that simply does not fit the remaining budget of the current flush stays
queued in FIFO order and is reported through `deferred_uploads`.

Texture identifiers use the same bounded token policy as the 1.8 resource layer: after trimming, they
must be non-empty and at most 128 characters. This keeps queue/residency diagnostics and fingerprints
bounded by the configured work limits rather than an unbounded identifier string.

## Duplicate suppression

Duplicate suppression is conservative. A digest becomes authoritative only after the backend submit
callback succeeds. Failed work stays queued and cannot poison the duplicate cache.

The duplicate key includes texture id, full/region identity, the complete
`RenderResourceDescriptor`, declared residency byte size and payload SHA-256. Reusing the same payload
bytes for a resized/reformatted texture or for a different logical residency size therefore causes a
real backend submission instead of an incorrect skip.

A successful full upload invalidates every remembered region digest for the texture. A successful
partial update invalidates every remembered full-texture digest and any overlapping region digests,
including digests authored under a previous descriptor. This avoids treating stale atlas regions as
unchanged after intersecting writes or a resource-shape change. Eviction clears all remembered
digests for that texture.

## Residency and eviction

Every successful upload establishes or refreshes a logical residency record. Its byte accounting uses
`resident_bytes` supplied to `enqueue(...)`, or `RenderResourceDescriptor.size_bytes` when available,
falling back to the upload payload size.

When a new/expanded texture would exceed the configured resident texture or byte limits, reclaimable
textures are selected deterministically by:

1. lowest creator priority;
2. oldest last-use sequence;
3. texture id as the final stable tie-breaker.

Pinned textures are never selected automatically. If no reclaimable entry can satisfy the budget,
`flush()` raises `residency-exhausted` and leaves the pending upload queued. Creators can adjust live
entries with `set_residency_priority()`, `pin()`, `mark_used()` and `evict_texture()`.

The optional eviction callback is invoked before logical accounting is removed. A backend eviction
failure raises `evict-failed`, leaves that entry resident and leaves the upload queued.

## Failure semantics

The upload queue uses stable `TextureUploadError.code` values for creator-visible failures. Backend
submit failure is wrapped as `submit-failed`; the head request remains queued, submitted counters do
not advance and no duplicate digest is installed. Retrying a later flush therefore retries the real
upload rather than silently dropping it.

If a bytes-like object reports a different size when the immutable staging snapshot is produced, the
queue refuses it with `payload-size-mismatch` instead of accepting ambiguous byte accounting.

## Diagnostics

`TextureUploadQueue.diagnostics()` exposes only portable numeric accounting: queued/submitted bytes,
full/partial uploads, duplicate skips, residency, evictions, deferrals, back-pressure, failures and
queue high-water marks. `state_fingerprint()` produces deterministic SHA-256 state identity from
request descriptors/metadata/digests, residency, duplicate-cache identity and diagnostics without
serializing raw payload bytes or callbacks.

See `examples/demo_render_uploads_1_8.py` for a runnable headless example and
`tools/benchmark_render_uploads_1_8.py` for the deterministic regression workload. Neither is an FPS
or physical GPU-throughput benchmark.
