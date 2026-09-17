import pytest

from swirengine.render_resources18 import RenderResourceDescriptor
from swirengine.render_uploads18 import TextureUploadQueue


def descriptor(*, width: int = 8, height: int = 8, size: int = 64):
    return RenderResourceDescriptor(
        "texture",
        "rgba8",
        width,
        height,
        usage="sampled",
        size_bytes=size,
    )


def test_duplicate_payload_with_changed_descriptor_is_resubmitted() -> None:
    submitted = []
    queue = TextureUploadQueue(submit=submitted.append)

    queue.enqueue("hero", descriptor(width=8), b"same")
    queue.flush()
    queue.enqueue("hero", descriptor(width=16), b"same")

    assert queue.flush() == 1
    assert len(submitted) == 2
    assert submitted[0].descriptor.width == 8
    assert submitted[1].descriptor.width == 16
    assert queue.diagnostics().duplicate_skips == 0


def test_duplicate_payload_with_changed_residency_size_is_resubmitted() -> None:
    submitted = []
    queue = TextureUploadQueue(submit=submitted.append)
    spec = descriptor(size=0)

    queue.enqueue("hero", spec, b"same", resident_bytes=16)
    queue.flush()
    queue.enqueue("hero", spec, b"same", resident_bytes=32)

    assert queue.flush() == 1
    assert len(submitted) == 2
    assert queue.residency()[0].bytes == 32
    assert queue.diagnostics().duplicate_skips == 0


def test_state_fingerprint_distinguishes_pending_descriptor_identity() -> None:
    first = TextureUploadQueue(submit=lambda _upload: None)
    second = TextureUploadQueue(submit=lambda _upload: None)
    first.enqueue("hero", descriptor(width=8), b"same")
    second.enqueue("hero", descriptor(width=16), b"same")

    assert first.state_fingerprint() != second.state_fingerprint()


def test_state_fingerprint_distinguishes_resident_descriptor_identity() -> None:
    first = TextureUploadQueue(submit=lambda _upload: None)
    second = TextureUploadQueue(submit=lambda _upload: None)
    first.enqueue("hero", descriptor(width=8), b"same")
    second.enqueue("hero", descriptor(width=16), b"same")
    first.flush()
    second.flush()

    assert first.state_fingerprint() != second.state_fingerprint()


def test_texture_identifier_uses_same_bounded_token_contract_as_1_8_resources() -> None:
    queue = TextureUploadQueue(submit=lambda _upload: None)

    with pytest.raises(ValueError, match="at most 128"):
        queue.enqueue("x" * 129, descriptor(), b"data")


def test_byte_backpressure_is_checked_before_mutable_payload_snapshot() -> None:
    queue = TextureUploadQueue(
        submit=lambda _upload: None,
        max_pending_bytes=4,
        max_bytes_per_flush=8,
    )
    queue.enqueue("first", descriptor(), b"1234")
    payload = bytearray(b"5678")

    with pytest.raises(Exception) as error:
        queue.enqueue("second", descriptor(), payload)

    assert getattr(error.value, "code", None) == "queue-bytes-full"
    assert queue.queued_uploads == 1
    assert queue.queued_bytes == 4
