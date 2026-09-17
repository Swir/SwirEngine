import pytest

from swirengine.upload_residency18 import (
    BoundedUploadQueue,
    TextureResidencyManager,
    UploadRequest,
    UploadResidencyError,
)


def request(
    asset_id: str,
    *,
    revision: int = 1,
    size: int = 64,
    priority: int = 0,
) -> UploadRequest:
    return UploadRequest(asset_id, revision, size, priority)


def test_upload_request_validates_metadata_and_is_portable() -> None:
    item = request("terrain/albedo", revision=3, size=512, priority=7)

    assert dict(item.portable()) == {
        "asset_id": "terrain/albedo",
        "revision": 3,
        "size_bytes": 512,
        "priority": 7,
        "kind": "texture",
    }
    with pytest.raises(ValueError):
        request("", size=1)
    with pytest.raises(ValueError):
        request("x", size=0)
    with pytest.raises(TypeError):
        UploadRequest("x", 0, 1, True)


def test_queue_suppresses_duplicate_and_older_pending_revisions() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=4, max_outstanding_bytes=512)

    assert queue.enqueue(request("a", revision=2))
    assert queue.enqueue(request("a", revision=2)) is False
    assert queue.enqueue(request("a", revision=1)) is False

    diagnostics = queue.diagnostics()
    assert diagnostics.pending_requests == 1
    assert diagnostics.outstanding_requests == 1
    assert diagnostics.duplicate_suppressed == 2


def test_queue_newer_pending_revision_supersedes_atomically() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=2, max_outstanding_bytes=100)
    queue.enqueue(request("a", revision=1, size=40))

    assert queue.enqueue(request("a", revision=2, size=80))
    assert queue.pending_snapshot() == (request("a", revision=2, size=80),)
    assert queue.diagnostics().outstanding_bytes == 80

    with pytest.raises(UploadResidencyError) as error:
        queue.enqueue(request("a", revision=3, size=120))
    assert error.value.code == "request-too-large"
    assert queue.pending_snapshot() == (request("a", revision=2, size=80),)


def test_queue_rejects_request_and_byte_backpressure_without_mutation() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=2, max_outstanding_bytes=100)
    queue.enqueue(request("a", size=50))
    queue.enqueue(request("b", size=40))

    with pytest.raises(UploadResidencyError) as error:
        queue.enqueue(request("c", size=5))
    assert error.value.code == "outstanding-requests"

    queue2 = BoundedUploadQueue(max_outstanding_requests=4, max_outstanding_bytes=100)
    queue2.enqueue(request("a", size=60))
    with pytest.raises(UploadResidencyError) as error:
        queue2.enqueue(request("b", size=50))
    assert error.value.code == "outstanding-bytes"
    assert queue2.diagnostics().outstanding_bytes == 60


def test_stage_batch_uses_priority_then_stable_enqueue_order() -> None:
    queue = BoundedUploadQueue(
        max_outstanding_requests=8,
        max_outstanding_bytes=1024,
        max_staging_bytes=256,
        max_batch_bytes=256,
        max_batch_requests=3,
    )
    queue.enqueue(request("low", size=32, priority=0))
    queue.enqueue(request("high-first", size=32, priority=10))
    queue.enqueue(request("high-second", size=32, priority=10))
    queue.enqueue(request("mid", size=32, priority=5))

    batch = queue.stage_batch()

    assert batch is not None
    assert [item.asset_id for item in batch.requests] == ["high-first", "high-second", "mid"]
    assert batch.total_bytes == 96
    assert [item.asset_id for item in queue.pending_snapshot()] == ["low"]


def test_stage_batch_skips_oversized_request_and_uses_fitting_work() -> None:
    queue = BoundedUploadQueue(
        max_outstanding_requests=4,
        max_outstanding_bytes=1024,
        max_staging_bytes=128,
        max_batch_bytes=128,
    )
    queue.enqueue(request("large", size=100, priority=10))
    queue.enqueue(request("small", size=32, priority=1))

    batch = queue.stage_batch(max_bytes=64)

    assert batch is not None
    assert [item.asset_id for item in batch.requests] == ["small"]
    assert [item.asset_id for item in queue.pending_snapshot()] == ["large"]


def test_staging_budget_is_explicit_backpressure() -> None:
    queue = BoundedUploadQueue(
        max_outstanding_requests=4,
        max_outstanding_bytes=1024,
        max_staging_bytes=64,
        max_batch_bytes=64,
    )
    queue.enqueue(request("a", size=64))
    first = queue.stage_batch()
    assert first is not None
    queue.enqueue(request("b", size=32))

    with pytest.raises(UploadResidencyError) as error:
        queue.stage_batch()

    assert error.value.code == "staging-backpressure"
    assert queue.diagnostics().staged_bytes == 64


def test_complete_batch_releases_outstanding_and_rejects_stale_batch() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=4, max_outstanding_bytes=512)
    queue.enqueue(request("a"))
    batch = queue.stage_batch()
    assert batch is not None

    completed = queue.complete_batch(batch.batch_id)

    assert completed == batch
    assert queue.diagnostics().outstanding_requests == 0
    with pytest.raises(UploadResidencyError) as error:
        queue.complete_batch(batch.batch_id)
    assert error.value.code == "stale-batch"


def test_abort_restores_staged_upload_with_original_order() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=4, max_outstanding_bytes=512)
    queue.enqueue(request("a", priority=1))
    queue.enqueue(request("b", priority=0))
    batch = queue.stage_batch(max_requests=1)
    assert batch is not None and batch.requests[0].asset_id == "a"

    queue.abort_batch(batch.batch_id)

    assert [item.asset_id for item in queue.pending_snapshot()] == ["a", "b"]
    assert queue.diagnostics().outstanding_requests == 2


def test_abort_drops_staged_revision_when_newer_pending_revision_exists() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=4, max_outstanding_bytes=512)
    queue.enqueue(request("a", revision=1))
    old_batch = queue.stage_batch()
    assert old_batch is not None
    queue.enqueue(request("a", revision=2))

    queue.abort_batch(old_batch.batch_id)

    assert queue.pending_snapshot() == (request("a", revision=2),)
    assert queue.diagnostics().outstanding_requests == 1


def test_staged_revision_suppresses_equal_or_older_enqueue() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=4, max_outstanding_bytes=512)
    queue.enqueue(request("a", revision=4))
    batch = queue.stage_batch()
    assert batch is not None

    assert queue.enqueue(request("a", revision=4)) is False
    assert queue.enqueue(request("a", revision=3)) is False
    assert queue.enqueue(request("a", revision=5)) is True


def test_residency_suppresses_duplicate_and_replaces_newer_revision() -> None:
    residency = TextureResidencyManager(max_resources=2, max_bytes=256)
    first = residency.admit(request("a", revision=2, size=64, priority=2))
    duplicate = residency.admit(request("a", revision=2, size=64, priority=2))
    replacement = residency.admit(request("a", revision=3, size=96, priority=3))

    assert first.admitted and not first.replaced
    assert duplicate.admitted is False
    assert replacement.admitted and replacement.replaced
    assert residency.resident_revision("a") == 3
    assert residency.diagnostics().resident_bytes == 96


def test_residency_evicts_lowest_priority_then_oldest_use() -> None:
    residency = TextureResidencyManager(max_resources=2, max_bytes=128)
    residency.admit(request("old-low", size=64, priority=1))
    residency.admit(request("new-low", size=64, priority=1))
    residency.touch("new-low")

    admission = residency.admit(request("incoming", size=64, priority=2))

    assert admission.evicted == ("old-low",)
    assert [entry.asset_id for entry in residency.snapshot()] == ["incoming", "new-low"]


def test_lower_priority_request_cannot_evict_higher_priority_resident() -> None:
    residency = TextureResidencyManager(max_resources=1, max_bytes=64)
    residency.admit(request("important", size=64, priority=10))

    with pytest.raises(UploadResidencyError) as error:
        residency.admit(request("background", size=64, priority=1))

    assert error.value.code == "residency-pressure"
    assert [entry.asset_id for entry in residency.snapshot()] == ["important"]


def test_pinned_resident_blocks_pressure_until_unpinned() -> None:
    residency = TextureResidencyManager(max_resources=1, max_bytes=64)
    residency.admit(request("pinned", size=64, priority=1), pinned=True)

    with pytest.raises(UploadResidencyError):
        residency.admit(request("replacement", size=64, priority=100))

    assert residency.set_pinned("pinned", False)
    admission = residency.admit(request("replacement", size=64, priority=100))
    assert admission.evicted == ("pinned",)


def test_residency_failed_admission_is_atomic_for_byte_pressure() -> None:
    residency = TextureResidencyManager(max_resources=3, max_bytes=100)
    residency.admit(request("high", size=60, priority=10))
    residency.admit(request("low", size=40, priority=1), pinned=True)
    before = residency.snapshot()

    with pytest.raises(UploadResidencyError):
        residency.admit(request("new", size=80, priority=5))

    assert residency.snapshot() == before
    assert residency.diagnostics().resident_bytes == 100


def test_residency_touch_changes_lru_tie_break_without_changing_priority() -> None:
    residency = TextureResidencyManager(max_resources=2, max_bytes=128)
    residency.admit(request("a", size=64, priority=1))
    residency.admit(request("b", size=64, priority=1))
    assert residency.touch("a")

    admission = residency.admit(request("c", size=64, priority=1))

    assert admission.evicted == ("b",)
    assert residency.touch("missing") is False


def test_explicit_evict_respects_pin_unless_forced() -> None:
    residency = TextureResidencyManager(max_resources=2, max_bytes=128)
    residency.admit(request("a", size=64), pinned=True)

    with pytest.raises(UploadResidencyError) as error:
        residency.evict("a")
    assert error.value.code == "resident-pinned"
    assert residency.evict("a", force=True)
    assert residency.evict("a", force=True) is False


def test_queue_and_residency_diagnostics_are_payload_free_numeric_contracts() -> None:
    queue = BoundedUploadQueue(max_outstanding_requests=4, max_outstanding_bytes=512)
    residency = TextureResidencyManager(max_resources=2, max_bytes=128)
    queue.enqueue(request("a"))
    batch = queue.stage_batch()
    assert batch is not None
    queue.complete_batch(batch.batch_id)
    residency.admit(batch.requests[0])

    assert all(isinstance(value, int) for value in queue.diagnostics().portable().values())
    assert all(isinstance(value, int) for value in residency.diagnostics().portable().values())
    assert tuple(dict(entry.portable()) for entry in residency.snapshot())[0]["asset_id"] == "a"
