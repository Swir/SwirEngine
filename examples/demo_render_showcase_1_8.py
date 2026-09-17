from __future__ import annotations

import json
from types import SimpleNamespace

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D, Text2D
from swirengine.math.types import Vec3
from swirengine.render_resources18 import RenderResourceDescriptor, TransientRenderResourcePool
from swirengine.render_showcase18 import (
    RenderShowcaseSettings,
    RenderShowcaseUpload,
    run_render_showcase,
)
from swirengine.render_uploads18 import TextureUploadQueue
from swirengine.renderer2_bridge18 import Renderer2CompatibilityBridge


class SourceShowcaseRenderer:
    """Tiny backend boundary used to demonstrate the 1.8 source-only showcase contract."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.width = 1280
        self.height = 720
        self.frames = 0

    def render_graph18(self, frame, scene, *, camera=None, clear_color=None) -> None:
        del frame, scene, camera, clear_color
        self.frames += 1


def scene(*objects):
    return SimpleNamespace(objects=list(objects))


def run_2d_showcase():
    descriptor = RenderResourceDescriptor(
        kind="texture",
        format="rgba8",
        width=8,
        height=8,
        size_bytes=256,
    )
    pool = TransientRenderResourcePool(
        create=lambda item: {"bytes": item.size_bytes},
        destroy=lambda resource: None,
        max_resources=4,
        max_bytes=4096,
    )
    queue = TextureUploadQueue(
        submit=lambda upload: None,
        max_pending_uploads=16,
        max_pending_bytes=4096,
        max_uploads_per_flush=16,
        max_bytes_per_flush=4096,
        max_resident_textures=4,
        max_resident_bytes=4096,
    )
    return run_render_showcase(
        Renderer2CompatibilityBridge(SourceShowcaseRenderer("2d")),
        lambda frame: scene(
            Rectangle2D(frame * 3, 24, 40, 20, layer=0),
            Text2D(f"frame {frame}", x=12, y=12, layer=1, screen_space=True),
        ),
        settings=RenderShowcaseSettings(frames=24),
        resource_pool=pool,
        resource_descriptors=(descriptor,),
        upload_queue=queue,
        uploads=(RenderShowcaseUpload("ui-atlas", descriptor, bytes(256)),),
    )


def run_3d_showcase():
    return run_render_showcase(
        Renderer2CompatibilityBridge(SourceShowcaseRenderer("3d")),
        lambda frame: scene(
            Cube3D(position=Vec3(float((frame % 5) - 2), 0.0, -5.0))
        ),
        camera_factory=lambda frame: Camera3D(),
        settings=RenderShowcaseSettings(frames=24),
    )


def main() -> None:
    reports = {
        "2d": dict(run_2d_showcase().portable()),
        "3d": dict(run_3d_showcase().portable()),
    }
    print(json.dumps(reports, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
