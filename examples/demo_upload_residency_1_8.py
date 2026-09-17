from swirengine.upload_residency18 import (
    BoundedUploadQueue,
    TextureResidencyManager,
    UploadRequest,
)


queue = BoundedUploadQueue(
    max_outstanding_requests=16,
    max_outstanding_bytes=16 * 1024 * 1024,
    max_staging_bytes=4 * 1024 * 1024,
    max_batch_bytes=2 * 1024 * 1024,
    max_batch_requests=4,
)
residency = TextureResidencyManager(max_resources=3, max_bytes=6 * 1024 * 1024)

for upload in (
    UploadRequest("ui/atlas", 1, 512 * 1024, priority=100),
    UploadRequest("world/rock-a", 1, 2 * 1024 * 1024, priority=20),
    UploadRequest("world/rock-b", 1, 2 * 1024 * 1024, priority=20),
    UploadRequest("world/grass", 1, 2 * 1024 * 1024, priority=5),
):
    queue.enqueue(upload)

while queue.diagnostics().pending_requests:
    batch = queue.stage_batch()
    assert batch is not None
    print("staging", batch.batch_id, [item.asset_id for item in batch.requests])

    # A renderer would upload the payloads represented by this metadata here.
    for item in batch.requests:
        admission = residency.admit(item, pinned=item.asset_id == "ui/atlas")
        print("resident", item.asset_id, "evicted", admission.evicted)

    queue.complete_batch(batch.batch_id)

# A higher-priority streaming texture can displace lower-priority resident content.
queue.enqueue(UploadRequest("world/hero-banner", 1, 2 * 1024 * 1024, priority=50))
batch = queue.stage_batch()
assert batch is not None
for item in batch.requests:
    print("priority admission", item.asset_id, residency.admit(item).evicted)
queue.complete_batch(batch.batch_id)

print("upload diagnostics", dict(queue.diagnostics().portable()))
print("residency diagnostics", dict(residency.diagnostics().portable()))
print("resident assets", [entry.asset_id for entry in residency.snapshot()])
