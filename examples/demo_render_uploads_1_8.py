from __future__ import annotations

from swirengine.render_resources18 import RenderResourceDescriptor
from swirengine.render_uploads18 import TextureUploadQueue, TextureUploadRegion


def main() -> None:
    submitted: list[str] = []
    evicted: list[str] = []

    queue = TextureUploadQueue(
        submit=lambda upload: submitted.append(
            f"{upload.texture_id}:{'partial' if upload.partial else 'full'}:{upload.byte_count}"
        ),
        evict=evicted.append,
        max_pending_uploads=8,
        max_pending_bytes=1024,
        max_uploads_per_flush=4,
        max_bytes_per_flush=512,
        max_resident_textures=2,
        max_resident_bytes=512,
    )
    texture = RenderResourceDescriptor(
        "texture",
        "rgba8",
        8,
        8,
        usage="sampled",
        size_bytes=256,
    )

    queue.enqueue("hero", texture, b"H" * 128, priority=10, pinned=True)
    queue.enqueue(
        "atlas",
        texture,
        b"A" * 64,
        region=TextureUploadRegion(0, 0, 4, 4),
        priority=1,
    )
    queue.flush()

    # The same atlas payload is known resident, so the second request is suppressed.
    queue.enqueue(
        "atlas",
        texture,
        b"A" * 64,
        region=TextureUploadRegion(0, 0, 4, 4),
        priority=1,
    )
    queue.flush()

    # Make atlas reclaimable, then demonstrate deterministic residency pressure.
    queue.enqueue("menu", texture, b"M" * 128, priority=5)
    queue.flush()

    diagnostics = queue.diagnostics()
    print("submitted:", submitted)
    print("evicted:", evicted)
    print("resident:", [entry.texture_id for entry in queue.residency()])
    print("diagnostics:", dict(diagnostics.portable()))
    print("state fingerprint:", queue.state_fingerprint())


if __name__ == "__main__":
    main()
