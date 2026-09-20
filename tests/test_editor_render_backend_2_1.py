from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from swirengine import Scene
from swirengine.editor_render_backend21 import (
    EditorRenderBackend21,
    ResizableFramebufferTarget,
)
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.primitives import Rectangle2D


class FakeResource:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload
        self.use_calls = 0
        self.release_calls = 0
        self.read_calls: list[dict[str, object]] = []

    def use(self) -> None:
        self.use_calls += 1

    def read(self, **kwargs) -> bytes:
        self.read_calls.append(kwargs)
        return self.payload

    def release(self) -> None:
        self.release_calls += 1


class FakeContext:
    def __init__(self) -> None:
        self.textures: list[FakeResource] = []
        self.depth_buffers: list[FakeResource] = []
        self.framebuffers: list[FakeResource] = []
        self.fbo = None

    def texture(self, size: tuple[int, int], components: int) -> FakeResource:
        assert components == 4
        resource = FakeResource()
        resource.size = size
        self.textures.append(resource)
        return resource

    def depth_renderbuffer(self, size: tuple[int, int]) -> FakeResource:
        resource = FakeResource()
        resource.size = size
        self.depth_buffers.append(resource)
        return resource

    def framebuffer(self, *, color_attachments, depth_attachment) -> FakeResource:
        assert color_attachments[-1] is self.textures[-1]
        assert depth_attachment is self.depth_buffers[-1]
        resource = FakeResource(bytes(range(18)))
        self.framebuffers.append(resource)
        return resource


class FakeRenderer:
    def __init__(self, ctx: FakeContext) -> None:
        self.ctx = ctx
        self.resize_calls: list[tuple[int, int]] = []
        self.render_calls = 0
        self.release_calls = 0

    def resize(self, width: int, height: int) -> None:
        self.resize_calls.append((width, height))

    def render(self, scene, *, camera=None) -> None:
        self.render_calls += 1

    def release(self) -> None:
        self.release_calls += 1


class FakeGlfw:
    def __init__(self) -> None:
        self.destroyed: list[object] = []

    def destroy_window(self, window: object) -> None:
        self.destroyed.append(window)


def test_resizable_target_reallocates_and_releases_superseded_resources() -> None:
    ctx = FakeContext()
    activations: list[bool] = []
    target = ResizableFramebufferTarget(
        ctx,
        2,
        2,
        activate=lambda: activations.append(True),
    )
    first_fbo = target.framebuffer
    first_color = ctx.textures[-1]
    first_depth = ctx.depth_buffers[-1]

    target.resize(3, 2)

    assert target.width == 3
    assert target.height == 2
    assert target.framebuffer is not first_fbo
    assert target.owns(first_fbo)
    assert first_fbo.release_calls == 0

    target.use()

    assert first_fbo.release_calls == 1
    assert first_color.release_calls == 1
    assert first_depth.release_calls == 1
    assert target.framebuffer.use_calls == 1
    assert activations


def test_resizable_target_noops_same_size_and_release_is_idempotent() -> None:
    ctx = FakeContext()
    target = ResizableFramebufferTarget(ctx, 4, 3)

    target.resize(4, 3)

    assert len(ctx.framebuffers) == 1
    target.release()
    target.release()
    assert ctx.framebuffers[0].release_calls == 1
    assert ctx.textures[0].release_calls == 1
    assert ctx.depth_buffers[0].release_calls == 1


def test_editor_backend_release_owns_only_its_window_and_gpu_resources() -> None:
    ctx = FakeContext()
    target = ResizableFramebufferTarget(ctx, 2, 2)
    renderer = FakeRenderer(ctx)
    glfw = FakeGlfw()
    context_release_calls: list[bool] = []
    ctx.release = lambda: context_release_calls.append(True)
    window = SimpleNamespace(name="editor")
    backend = EditorRenderBackend21(
        ctx=ctx,
        renderer=renderer,
        target=target,
        window=window,
        glfw_module=glfw,
    )

    backend.release()
    backend.release()

    assert renderer.release_calls == 1
    assert context_release_calls == [True]
    assert glfw.destroyed == [window]


def test_real_live_backend_captures_2d_scene_on_desktop_runner() -> None:
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        pytest.skip("Linux runner has no desktop display for a hidden GLFW context")

    backend = EditorRenderBackend21.create(16, 12)
    try:
        scene = Scene()
        scene.add(Rectangle2D(0.0, 0.0, 8.0, 8.0, name="Smoke"))
        image = backend.viewport.capture(
            scene,
            16,
            12,
            camera=Camera2D(),
            mode="2d",
        )
        assert image.width == 16
        assert image.height == 12
        assert len(image.rgb) == 16 * 12 * 3
    finally:
        backend.release()
