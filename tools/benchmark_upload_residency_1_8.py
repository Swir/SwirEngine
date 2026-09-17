from __future__ import annotations

import time

from swirengine.upload_residency18 import (
    BoundedUploadQueue,
    TextureResidencyManager,
    UploadRequest,
)

FRAMES = 250
ASSETS = 256
REQUESTS_PER_FRAME = 32
BUDGET_SECONDS = 5.0


def main() -> None:
    queue = BoundedUploadQueue(
        max_outstanding_requests=1024,
        max_outstanding_bytes=256 * 1024 * 1024,
        max_staging_bytes=8 * 1024 * 1024,
        max_batch_bytes=2 * 1024 * 1024,
        max_batch_requests=64,
    )
    residency = TextureResidencyManager(
        max_resources=128,
        max_bytes=64 * 1024 * 1024,
    )

    started = time.perf_counter()
    logical_requests = 0
    staged_requests = 0
    for frame in range(FRAMES):
        for offset in range(REQUESTS_PER_FRAME):
            asset_index = (frame * REQUESTS_PER_FRAME + offset) % ASSETS
            revision = frame // 8 + 1
            accepted = queue.enqueue(
                UploadRequest(
                    asset_id=f"texture-{asset_index:04d}",
                    revision=revision,
                    size_bytes=64 * 1024 + (asset_index % 8) * 4096,
                    priority=asset_index % 5,
                )
            )
            logical_requests += 1
            if not accepted:
                continue

        while queue.diagnostics().pending_requests:
            batch = queue.stage_batch()
            if batch is None:
                break
            for item in batch.requests:
                residency.admit(item)
                staged_requests += 1
            queue.complete_batch(batch.batch_id)

        for touch_index in range(16):
            residency.touch(f"texture-{(frame + touch_index) % ASSETS:04d}")

    elapsed = time.perf_counter() - started
    queue_diag = queue.diagnostics()
    residency_diag = residency.diagnostics()

    assert queue_diag.outstanding_requests == 0
    assert queue_diag.outstanding_bytes == 0
    assert residency_diag.resident_resources <= 128
    assert residency_diag.resident_bytes <= 64 * 1024 * 1024
    assert elapsed < BUDGET_SECONDS, (
        f"upload/residency workload took {elapsed:.4f}s, budget is {BUDGET_SECONDS:.1f}s"
    )
    print(
        "upload-residency-1.8 workload:",
        f"logical_requests={logical_requests}",
        f"staged_requests={staged_requests}",
        f"resident={residency_diag.resident_resources}",
        f"evictions={residency_diag.evictions}",
        f"elapsed={elapsed:.4f}s",
    )


if __name__ == "__main__":
    main()
