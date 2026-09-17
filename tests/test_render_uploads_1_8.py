import pytest

from swirengine.render_resources18 import RenderResourceDescriptor
from swirengine.render_uploads18 import (
    TextureUploadError,
    TextureUploadQueue,
    TextureUploadRegion,
)


def descriptor(*, width: int = 8, height: int = 8, layers: int = 1, size: int = 64):
    return RenderResourceDescriptor(
        "texture",
        "rgba8",
        width,
        height,
        layers=layers,
        usage="sampled",
        size_bytes=size,
    )


def test_full_upload_snapshots_mutable_payload_and_submits_fifo() -> None:
    submitted = []
    queue = TextureUploadQueue(submit=submitted.append, max_bytes_per_flush=32)
    payload = bytearray(b"abcd")

    queued = queue.enqueue("hero", descriptor(), payload)
    payload[:] = b"zzzz"
    count = queue.flush()

    assert count == 1
    assert queued.payload == b"abcd"
    assert submitted[0].payload == b"abcd"
    assert queue.diagnostics().submitted_bytes == 4


def test_partial_region_validates_layer_and_texture_bounds() -> None:
    queue = TextureUploadQueue(submit=lambda _upload: None)
    spec = descriptor(layers=2)

    queue.enqueue("atlas", spec, b"tile", region=TextureUploadRegion(4, 4, 4, 4, 1))

    with pytest.raises(TextureUploadError) as width_error:
        queue.enqueue("atlas", spec, b"tile", region=TextureUploadRegion(7, 0, 2, 2))
    assert width_error.value.code == "region-out-of-bounds"

    with pytest.raises(TextureUploadError) as layer_error:
        queue.enqueue("atlas", spec, b"tile", region=TextureUploadRegion(0, 0, 2, 2, 2))
    assert layer_error.value.code == "region-out-of-bounds"


def test_non_texture_and_empty_uploads_are_rejected() -> None:
    queue = TextureUploadQueue(submit=lambda _upload: None)
    buffer = RenderResourceDescriptor("buffer", "raw", 1, 1, size_bytes=16)

    with pytest.raises(TextureUploadError) as kind_error:
        queue.enqueue("buffer", buffer, b"1234")
    assert kind_error.value.code == "not-a-texture"

    with pytest.raises(TextureUploadError) as empty_error:
        queue.enqueue("texture", descriptor(), b"")
    assert empty_error.value.code == "empty-upload"


def test_duplicate_full_upload_is_skipped_only_after_success() -> None:
    submitted = []
    queue = TextureUploadQueue(submit=submitted.append)

    queue.enqueue("hero", descriptor(), b"same")
    queue.enqueue("hero", descriptor(), b"same")
    assert queue.flush() == 1

    diagnostics = queue.diagnostics()
    assert len(submitted) == 1
    assert diagnostics.duplicate_skips == 1
    assert diagnostics.duplicate_skip_bytes == 4


def test_partial_upload_invalidates_overlapping_region_digest() -> None:
    submitted = []
    queue = TextureUploadQueue(submit=submitted.append)
    spec = descriptor()
    first = TextureUploadRegion(0, 0, 4, 4)
    overlap = TextureUploadRegion(2, 2, 4, 4)

    queue.enqueue("atlas", spec, b"AAAA", region=first)
    queue.flush()
    queue.enqueue("atlas", spec, b"AAAA", region=first)
    queue.flush()
    assert queue.diagnostics().duplicate_skips == 1

    queue.enqueue("atlas", spec, b"BBBB", region=overlap)
    queue.flush()
    queue.enqueue("atlas", spec, b"AAAA", region=first)
    queue.flush()

    assert len(submitted) == 3


def test_full_and_partial_updates_invalidate_each_others_duplicate_assumptions() -> None:
    submitted = []
    queue = TextureUploadQueue(submit=submitted.append)
    spec = descriptor()
    region = TextureUploadRegion(0, 0, 2, 2)

    queue.enqueue("atlas", spec, b"full")
    queue.flush()
    queue.enqueue("atlas", spec, b"tile", region=region)
    queue.flush()
    queue.enqueue("atlas", spec, b"full")
    queue.flush()
    queue.enqueue("atlas", spec, b"tile", region=region)
    queue.flush()

    assert len(submitted) == 4
    assert queue.diagnostics().duplicate_skips == 0


def test_flush_budget_defers_fifo_work_without_exceeding_byte_budget() -> None:
    submitted = []
    queue = TextureUploadQueue(
        submit=submitted.append,
        max_uploads_per_flush=8,
        max_bytes_per_flush=6,
    )
    spec = descriptor()
    queue.enqueue("a", spec, b"1111")
    queue.enqueue("b", spec, b"2222")

    assert queue.flush() == 1
    assert [upload.texture_id for upload in submitted] == ["a"]
    assert queue.queued_uploads == 1
    assert queue.diagnostics().deferred_uploads == 1
    assert queue.flush() == 1
    assert [upload.texture_id for upload in submitted] == ["a", "b"]


def test_single_upload_larger_than_flush_budget_is_rejected_instead_of_starving() -> None:
    queue = TextureUploadQueue(submit=lambda _upload: None, max_bytes_per_flush=3)

    with pytest.raises(TextureUploadError) as error:
        queue.enqueue("large", descriptor(), b"1234")

    assert error.value.code == "upload-too-large"
    assert queue.queued_uploads == 0


def test_pending_count_and_byte_backpressure_are_explicit() -> None:
    count_queue = TextureUploadQueue(
        submit=lambda _upload: None,
        max_pending_uploads=1,
        max_pending_bytes=8,
    )
    count_queue.enqueue("a", descriptor(), b"1234")
    with pytest.raises(TextureUploadError) as count_error:
        count_queue.enqueue("b", descriptor(), b"1")
    assert count_error.value.code == "queue-full"

    byte_queue = TextureUploadQueue(
        submit=lambda _upload: None,
        max_pending_uploads=4,
        max_pending_bytes=5,
    )
    byte_queue.enqueue("a", descriptor(), b"1234")
    with pytest.raises(TextureUploadError) as byte_error:
        byte_queue.enqueue("b", descriptor(), b"12")
    assert byte_error.value.code == "queue-bytes-full"
    assert byte_queue.diagnostics().backpressure_rejections == 1


def test_submit_failure_retains_head_and_does_not_install_duplicate_digest() -> None:
    attempts = []
    fail = True

    def submit(upload):
        nonlocal fail
        attempts.append(upload.texture_id)
        if fail:
            raise RuntimeError("device busy")

    queue = TextureUploadQueue(submit=submit)
    queue.enqueue("hero", descriptor(), b"pixels")

    with pytest.raises(TextureUploadError) as error:
        queue.flush()
    assert error.value.code == "submit-failed"
    assert queue.queued_uploads == 1
    assert queue.diagnostics().submitted_uploads == 0

    fail = False
    assert queue.flush() == 1
    queue.enqueue("hero", descriptor(), b"pixels")
    assert queue.flush() == 0
    assert attempts == ["hero", "hero"]


def test_residency_evicts_lowest_priority_then_oldest_deterministically() -> None:
    evicted = []
    queue = TextureUploadQueue(
        submit=lambda _upload: None,
        evict=evicted.append,
        max_resident_textures=2,
        max_resident_bytes=20,
    )
    spec = descriptor(size=10)
    queue.enqueue("important", spec, b"a", priority=10)
    queue.enqueue("background", spec, b"b", priority=0)
    queue.flush()

    queue.enqueue("new", spec, b"c", priority=5)
    queue.flush()

    assert evicted == ["background"]
    assert [entry.texture_id for entry in queue.residency()] == ["important", "new"]
    assert queue.diagnostics().evicted_bytes == 10


def test_pinned_residency_causes_explicit_pressure_without_dropping_upload() -> None:
    queue = TextureUploadQueue(
        submit=lambda _upload: None,
        max_resident_textures=1,
        max_resident_bytes=10,
    )
    spec = descriptor(size=10)
    queue.enqueue("pinned", spec, b"a", pinned=True)
    queue.flush()
    queue.enqueue("waiting", spec, b"b")

    with pytest.raises(TextureUploadError) as error:
        queue.flush()

    assert error.value.code == "residency-exhausted"
    assert queue.queued_uploads == 1
    assert queue.residency()[0].texture_id == "pinned"


def test_eviction_failure_keeps_residency_and_pending_upload_coherent() -> None:
    def fail_evict(_texture_id):
        raise RuntimeError("backend refused")

    queue = TextureUploadQueue(
        submit=lambda _upload: None,
        evict=fail_evict,
        max_resident_textures=1,
        max_resident_bytes=10,
    )
    spec = descriptor(size=10)
    queue.enqueue("old", spec, b"a")
    queue.flush()
    queue.enqueue("new", spec, b"b")

    with pytest.raises(TextureUploadError) as error:
        queue.flush()

    assert error.value.code == "evict-failed"
    assert queue.queued_uploads == 1
    assert queue.residency()[0].texture_id == "old"
    assert queue.diagnostics().eviction_failures == 1


def test_pin_priority_mark_used_and_manual_evict_are_creator_controlled() -> None:
    evicted = []
    queue = TextureUploadQueue(submit=lambda _upload: None, evict=evicted.append)
    queue.enqueue("hero", descriptor(), b"data")
    queue.flush()

    queue.set_residency_priority("hero", 20)
    queue.pin("hero")
    queue.mark_used("hero")
    entry = queue.residency()[0]
    assert entry.priority == 20
    assert entry.pinned is True
    assert entry.last_touch > 1

    with pytest.raises(TextureUploadError) as pinned_error:
        queue.evict_texture("hero")
    assert pinned_error.value.code == "texture-pinned"

    queue.pin("hero", False)
    queue.evict_texture("hero")
    assert evicted == ["hero"]
    assert queue.residency() == ()


def test_residency_byte_growth_evicts_other_texture_before_submit() -> None:
    evicted = []
    queue = TextureUploadQueue(
        submit=lambda _upload: None,
        evict=evicted.append,
        max_resident_textures=4,
        max_resident_bytes=18,
    )
    small = descriptor(size=8)
    larger = descriptor(size=12)
    queue.enqueue("grow", small, b"a", priority=5)
    queue.enqueue("victim", small, b"b", priority=0)
    queue.flush()

    queue.enqueue("grow", larger, b"c", priority=5)
    queue.flush()

    assert evicted == ["victim"]
    residency = queue.residency()
    assert len(residency) == 1
    assert residency[0].texture_id == "grow"
    assert residency[0].bytes == 12


def test_state_fingerprint_and_diagnostics_are_deterministic_portable_data() -> None:
    def build():
        queue = TextureUploadQueue(submit=lambda _upload: None)
        queue.enqueue("hero", descriptor(), b"data", priority=2)
        queue.flush()
        queue.enqueue("atlas", descriptor(), b"tile", region=TextureUploadRegion(1, 1, 2, 2))
        return queue

    first = build()
    second = build()

    assert first.state_fingerprint() == second.state_fingerprint()
    portable = first.diagnostics().portable()
    assert portable["resident_textures"] == 1
    assert portable["queued_uploads"] == 1
    assert portable["queue_high_water_uploads"] == 1
