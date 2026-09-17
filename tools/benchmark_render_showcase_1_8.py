from __future__ import annotations

import argparse
import time
from types import SimpleNamespace

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.math.types import Vec3
from swirengine.render_resources18 import RenderResourceDescriptor, TransientRenderResourcePool
from swirengine.render_showcase18 import (
    RenderShowcaseSettings,
    RenderShowcaseUpload,
    run_render_showcase,
)
from swirengine.render_uploads18 import TextureUploadQueue
from swirengine.renderer2_bridge18 import Renderer2CompatibilityBridge


class HeadlessGraphRenderer:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.width = 1280
        self.height = 720
        self.frames = 0

    def render_graph18(self, frame, scene, *, camera=None, clear_color=None) -> None:
        del frame, scene, camera, clear_color
        self.frames += 1


def _scene(*objects):
    return SimpleNamespace(objects=list(objects))


def _run_2d(frames: int):
    descriptor = RenderResourceDescriptor(
        kind="texture",
        format="rgba8",
        width=8,
        height=8,
        size_bytes=256,
    )
    pool = TransientRenderResourcePool(
        create=lambda item: ("resource", item.size_bytes),
        destroy=lambda resource: None,
        max_resources=4,
        max_bytes=4096,
    )
    queue = TextureUploadQueue(
        submit=lambda upload: None,
        max_pending_uploads=32,
        max_pending_bytes=8192,
        max_uploads_per_flush=32,
        max_bytes_per_flush=8192,
        max_resident_textures=4,
        max_resident_bytes=4096,
    )
    renderer = HeadlessGraphRenderer("2d")
    report = run_render_showcase(
        Renderer2CompatibilityBridge(renderer),
        lambda frame: _scene(
            Rectangle2D(frame % 128, (frame * 3) % 96, 16, 16, layer=0),
            Rectangle2D((frame * 5) % 128, frame % 96, 8, 8, layer=1),
        ),
        settings=RenderShowcaseSettings(frames=frames),
        resource_pool=pool,
        resource_descriptors=(descriptor,),
        upload_queue=queue,
        uploads=(RenderShowcaseUpload("showcase-atlas", descriptor, bytes(256)),),
    )
    assert report.clean_frames == frames
    assert report.graph_backend_frames == frames
    assert report.resource_reuses == frames - 1
    assert report.upload_submissions == 1
    assert report.duplicate_upload_skips == frames - 1
    return report


def _run_3d(frames: int):
    renderer = HeadlessGraphRenderer("3d")
    report = run_render_showcase(
        Renderer2CompatibilityBridge(renderer),
        lambda frame: _scene(
            Cube3D(position=Vec3(float(frame % 7), 0.0, -4.0))
        ),
        camera_factory=lambda frame: Camera3D(),
        settings=RenderShowcaseSettings(frames=frames),
    )
    assert report.clean_frames == frames
    assert report.graph_backend_frames == frames
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=1200)
    parser.add_argument("--ceiling-seconds", type=float, default=10.0)
    args = parser.parse_args()
    if args.frames < 1:
        raise SystemExit("--frames must be >= 1")
    if args.ceiling_seconds <= 0:
        raise SystemExit("--ceiling-seconds must be > 0")

    started = time.perf_counter()
    report_2d = _run_2d(args.frames)
    report_3d = _run_3d(args.frames)
    elapsed = time.perf_counter() - started
    if elapsed > args.ceiling_seconds:
        raise SystemExit(
            f"render showcase workload took {elapsed:.4f}s, "
            f"exceeding {args.ceiling_seconds:.1f}s ceiling"
        )
    print(
        "render-showcase-1.8:",
        f"{args.frames * 2} frames",
        f"{elapsed:.4f}s",
        f"2d={report_2d.workload_fingerprint[:12]}",
        f"3d={report_3d.workload_fingerprint[:12]}",
    )


if __name__ == "__main__":
    main()
