from __future__ import annotations

import importlib.util
import os
import sys
from types import SimpleNamespace

import pytest
from typing_extensions import Self

import swirengine.editor_render_backend21 as render_backend_module
from swirengine import Scene
from swirengine.editor_render_backend21 import (
    EditorRenderBackend21,
    EditorRenderBackendUnavailable,
    ResizableFramebufferTarget,
)
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.math.types import Vec3


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


class FakeStandaloneContext(FakeContext):
    def __init__(self) -> None:
        super().__init__()
        self.enter_calls = 0
        self.exit_calls = 0
        self.release_calls = 0

    def __enter__(self) -> Self:
        self.enter_calls += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.exit_calls += 1

    def release(self) -> None:
        self.release_calls += 1


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
    VISIBLE = 1
    FALSE = 0
    CONTEXT_VERSION_MAJOR = 2
    CONTEXT_VERSION_MINOR = 3
    OPENGL_PROFILE = 4
    OPENGL_CORE_PROFILE = 5
    OPENGL_FORWARD_COMPAT = 6
    TRUE = 1

    def __init__(self) -> None:
        self.init_calls = 0
        self.hints: list[tuple[int, int]] = []
        self.created: list[object] = []
        self.current: list[object] = []
        self.destroyed: list[object] = []

    def init(self) -> bool:
        self.init_calls += 1
        return True

    def window_hint(self, hint: int, value: int) -> None:
        self.hints.append((hint, value))

    def create_window(self, width: int, height: int, title: str, monitor, share):
        assert (width, height, title, monitor, share) == (
            16,
            16,
            "SwirEditor Renderer",
            None,
            None,
        )
        window = SimpleNamespace(name="editor")
        self.created.append(window)
        return window

    def make_context_current(self, window: object) -> None:
        self.current.append(window)

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


def test_editor_backend_create_uses_standalone_offscreen_context(monkeypatch) -> None:
    ctx = FakeStandaloneContext()
    renderer = FakeRenderer(ctx)
    requested_versions: list[int] = []

    def create_standalone_context(*, require: int):
        requested_versions.append(require)
        return ctx

    monkeypatch.setattr(render_backend_module.sys, "platform", "darwin")
    monkeypatch.setitem(
        sys.modules,
        "moderngl",
        SimpleNamespace(create_standalone_context=create_standalone_context),
    )
    monkeypatch.setattr(render_backend_module, "Renderer", lambda *_args: renderer)

    backend = EditorRenderBackend21.create(6, 4)

    assert requested_versions == [330]
    assert backend.window is None
    assert backend.glfw is None
    assert (backend.target.width, backend.target.height) == (6, 4)
    assert ctx.enter_calls >= 1

    backend.release()

    assert renderer.release_calls == 1
    assert ctx.exit_calls == 1
    assert ctx.release_calls == 1


def test_editor_backend_create_uses_hidden_glfw_context_off_macos(monkeypatch) -> None:
    ctx = FakeContext()
    renderer = FakeRenderer(ctx)
    glfw = FakeGlfw()
    requested_versions: list[int] = []
    context_release_calls: list[bool] = []
    ctx.release = lambda: context_release_calls.append(True)

    def create_context(*, require: int):
        requested_versions.append(require)
        return ctx

    monkeypatch.setattr(render_backend_module.sys, "platform", "linux")
    monkeypatch.setitem(
        sys.modules,
        "moderngl",
        SimpleNamespace(create_context=create_context),
    )
    monkeypatch.setitem(sys.modules, "glfw", glfw)
    monkeypatch.setattr(render_backend_module, "Renderer", lambda *_args: renderer)

    backend = EditorRenderBackend21.create(7, 5)

    assert requested_versions == [330]
    assert glfw.init_calls == 1
    assert backend.window is glfw.created[0]
    assert backend.glfw is glfw
    assert glfw.current
    assert (backend.target.width, backend.target.height) == (7, 5)

    backend.release()

    assert renderer.release_calls == 1
    assert context_release_calls == [True]
    assert glfw.destroyed == [backend.window]


def test_real_live_backend_captures_2d_and_3d_scenes_on_desktop_runner() -> None:
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        pytest.skip("Linux runner has no desktop display for the standalone X11 context")
    if importlib.util.find_spec("moderngl") is None:
        pytest.skip(
            "source environment has no ModernGL; Windows CPython 3.14 is validated from "
            "the vendored platform wheel instead"
        )

    try:
        backend = EditorRenderBackend21.create(16, 12)
    except EditorRenderBackendUnavailable as exc:
        message = str(exc)
        known_hosted_windows_gap = sys.platform.startswith("win") and os.environ.get(
            "GITHUB_ACTIONS"
        ) == "true" and (
            "driver does not appear to support OpenGL" in message
            or "Cannot detect window with OpenGL support" in message
        )
        if known_hosted_windows_gap:
            pytest.skip(
                "GitHub Windows hosted runner has no usable WGL 3.3 driver; the Windows "
                "backend path is covered by the mocked context contract and the dedicated "
                "CPython 3.14 packaging/runtime probe"
            )
        raise

    try:
        scene_2d = Scene()
        scene_2d.add(Rectangle2D(0.0, 0.0, 8.0, 8.0, name="Smoke2D"))
        image_2d = backend.viewport.capture(
            scene_2d,
            16,
            12,
            camera=Camera2D(),
            mode="2d",
        )
        assert (image_2d.width, image_2d.height, len(image_2d.rgb)) == (16, 12, 576)

        scene_3d = Scene()
        scene_3d.add(Cube3D(position=Vec3(0.0, 0.0, -3.0), name="Smoke3D"))
        image_3d = backend.viewport.capture(
            scene_3d,
            20,
            14,
            camera=Camera3D(),
            mode="3d",
        )
        assert (image_3d.width, image_3d.height, len(image_3d.rgb)) == (20, 14, 840)
    finally:
        backend.release()
