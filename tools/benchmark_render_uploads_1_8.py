from __future__ import annotations

import time

from swirengine.render_resources18 import RenderResourceDescriptor
from swirengine.render_uploads18 import TextureUploadQueue, TextureUploadRegion

TEXTURES = 64
FRAMES = 120
UPLOAD_BYTES = 256
BUDGET_SECONDS = 5.0


def main() -> None:
    submitted = 0
    submitted_bytes = 0

    def submit(upload) -> None:
        nonlocal submitted, submitted_bytes
        submitted += 1
        submitted_bytes += upload.byte_count

    queue = TextureUploadQueue(
        submit=submit,
        max_pending_uploads=TEXTURES * 2,
        max_pending_bytes=TEXTURES * UPLOAD_BYTES * 2,
        max_uploads_per_flush=TEXTURES,
        max_bytes_per_flush=TEXTURES * UPLOAD_BYTES,
        max_resident_textures=TEXTURES,
        max_resident_bytes=TEXTURES * 4096,
    )
    spec = RenderResourceDescriptor(
        "texture",
        "rgba8",
        32,
        32,
        usage="sampled",
        size_bytes=4096,
    )
    region = TextureUploadRegion(0, 0, 8, 8)

    started = time.perf_counter()
    for frame in range(FRAMES):
        generation = frame // 2
        for texture in range(TEXTURES):
            value = (generation + texture) % 251
            payload = bytes([value]) * UPLOAD_BYTES
            queue.enqueue(
                f"atlas-{texture}",
                spec,
                payload,
                region=region,
                priority=texture % 4,
            )
        queue.flush()
    elapsed = time.perf_counter() - started

    diagnostics = queue.diagnostics()
    operations = TEXTURES * FRAMES
    expected_submissions = TEXTURES * ((FRAMES + 1) // 2)
    expected_skips = operations - expected_submissions

    if queue.queued_uploads != 0:
        raise RuntimeError("upload workload left queued work behind")
    if diagnostics.submitted_uploads != expected_submissions:
        raise RuntimeError(
            "duplicate suppression changed unexpectedly: "
            f"submitted={diagnostics.submitted_uploads}, expected={expected_submissions}"
        )
    if diagnostics.duplicate_skips != expected_skips:
        raise RuntimeError(
            "duplicate skip count changed unexpectedly: "
            f"skips={diagnostics.duplicate_skips}, expected={expected_skips}"
        )
    if diagnostics.resident_textures != TEXTURES:
        raise RuntimeError("upload workload did not retain the expected texture working set")
    if submitted != expected_submissions:
        raise RuntimeError("backend submission accounting diverged from diagnostics")
    if submitted_bytes != expected_submissions * UPLOAD_BYTES:
        raise RuntimeError("backend submitted byte accounting diverged")
    if elapsed > BUDGET_SECONDS:
        raise RuntimeError(
            f"texture upload workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )

    print(
        "render-uploads-1.8 workload:",
        f"operations={operations}",
        f"submitted={diagnostics.submitted_uploads}",
        f"duplicate_skips={diagnostics.duplicate_skips}",
        f"resident_textures={diagnostics.resident_textures}",
        f"elapsed={elapsed:.4f}s",
    )


if __name__ == "__main__":
    main()
