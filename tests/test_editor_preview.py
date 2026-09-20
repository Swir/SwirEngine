from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from swirengine import Scene
from swirengine.editor_preview import (
    EditorPreviewSession,
    EditorViewportImage,
    RendererViewportBridge,
)
from swirengine.editor_runtime import EditorRuntimeMode, EditorRuntimeSession
from swirengine.editor_workspace import EditorWorkspace
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class MovingActor:
    name: str
    x: float = 0.0
    enabled: bool = True

    def update(self, dt: float) -> None:
        self.x += dt * 10.0


def serializer() -> SceneSerializer:
    registry = SceneCodecRegistry.default()
    registry.register(MovingActor)
    return SceneSerializer(registry)


class FakeFramebuffer:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []
        self.use_calls = 0

    def use(self) -> None:
        self.use_calls += 1

    def read(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class FakeResizableFramebuffer(FakeFramebuffer):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.resize_calls: list[tuple[int, int]] = []
        self.activate_calls = 0
        self.owned: set[int] = set()

    def activate(self) -> None:
        self.activate_calls += 1

    def resize(self, width: int, height: int) -> None:
        self.resize_calls.append((width, height))

    def owns(self, framebuffer: object) -> bool:
        return id(framebuffer) in self.owned


class FakeRenderer:
    def __init__(self, framebuffer: FakeFramebuffer) -> None:
        self.ctx = SimpleNamespace(screen=framebuffer, fbo=framebuffer)
        self.mode = "2d"
        self.resized: list[tuple[int, int]] = []
        self.rendered: list[tuple[Scene, object | None]] = []

    def resize(self, width: int, height: int) -> None:
        self.resized.append((width, height))

    def render(self, scene: Scene, *, camera=None) -> None:
        self.rendered.append((scene, camera))


def test_viewport_image_validates_payload_and_builds_ppm():
    image = EditorViewportImage(2, 1, b"\x01\x02\x03\x04\x05\x06")
    assert image.to_ppm() == b"P6\n2 1\n255\n\x01\x02\x03\x04\x05\x06"

    with pytest.raises(ValueError, match="payload"):
        EditorViewportImage(2, 1, b"short")


def test_renderer_viewport_bridge_renders_and_flips_framebuffer_rows():
    bottom = bytes((1, 2, 3, 4, 5, 6))
    top = bytes((7, 8, 9, 10, 11, 12))
    framebuffer = FakeFramebuffer(bottom + top)
    renderer = FakeRenderer(framebuffer)
    bridge = RendererViewportBridge(renderer)
    scene = Scene()

    image = bridge.capture(scene, 2, 2)

    assert renderer.resized == [(2, 2)]
    assert renderer.rendered == [(scene, None)]
    assert framebuffer.use_calls == 1
    assert framebuffer.calls == [
        {"viewport": (0, 0, 2, 2), "components": 3, "alignment": 1}
    ]
    assert image.rgb == top + bottom


def test_renderer_viewport_bridge_resizes_dynamic_target_before_capture():
    payload = bytes(range(18))
    screen = FakeFramebuffer(payload)
    target = FakeResizableFramebuffer(payload)
    renderer = FakeRenderer(screen)
    bridge = RendererViewportBridge(renderer, framebuffer=target)

    image = bridge.capture(Scene(), 3, 2)

    assert image.width == 3
    assert image.height == 2
    assert target.activate_calls >= 1
    assert target.resize_calls == [(3, 2)]
    assert target.use_calls == 1
    assert renderer.resized == [(3, 2)]


def test_renderer_viewport_bridge_binds_target_restores_previous_and_syncs_mode_camera():
    payload = bytes(range(12))
    screen = FakeFramebuffer(payload)
    target = FakeFramebuffer(payload)
    previous = FakeFramebuffer(payload)
    renderer = FakeRenderer(screen)
    renderer.ctx.fbo = previous
    bridge = RendererViewportBridge(renderer, framebuffer=target)
    camera = object()
    scene = Scene()

    image = bridge.capture(scene, 2, 2, camera=camera, mode="3d")

    assert image.width == 2
    assert image.height == 2
    assert renderer.mode == "3d"
    assert renderer.rendered == [(scene, camera)]
    assert target.use_calls == 1
    assert previous.use_calls == 1
    assert screen.use_calls == 0


def test_renderer_viewport_bridge_does_not_restore_target_owned_previous_fbo():
    payload = bytes(range(12))
    screen = FakeFramebuffer(payload)
    target = FakeResizableFramebuffer(payload)
    previous = FakeFramebuffer(payload)
    target.owned.add(id(previous))
    renderer = FakeRenderer(screen)
    renderer.ctx.fbo = previous
    bridge = RendererViewportBridge(renderer, framebuffer=target)

    bridge.capture(Scene(), 2, 2)

    assert previous.use_calls == 0


def test_renderer_viewport_bridge_restores_previous_framebuffer_after_render_failure():
    payload = bytes(range(12))
    screen = FakeFramebuffer(payload)
    target = FakeFramebuffer(payload)
    previous = FakeFramebuffer(payload)
    renderer = FakeRenderer(screen)
    renderer.ctx.fbo = previous

    def fail_render(scene: Scene, *, camera=None) -> None:
        raise RuntimeError("render failed")

    renderer.render = fail_render
    bridge = RendererViewportBridge(renderer, framebuffer=target)

    with pytest.raises(RuntimeError, match="render failed"):
        bridge.capture(Scene(), 2, 2)

    assert target.use_calls == 1
    assert previous.use_calls == 1


def test_renderer_viewport_bridge_rejects_invalid_mode_and_framebuffer_payload():
    renderer = FakeRenderer(FakeFramebuffer(b"bad"))
    bridge = RendererViewportBridge(renderer)

    with pytest.raises(ValueError, match="unsupported renderer mode"):
        bridge.capture(Scene(), 2, 2, mode="vr")
    with pytest.raises(RuntimeError, match="unexpected RGB"):
        bridge.capture(Scene(), 2, 2)


def test_preview_play_pause_step_stop_preserves_edit_scene():
    scene = Scene()
    actor = scene.add(MovingActor("Player", x=2.0))
    workspace = EditorWorkspace(scene)
    runtime = EditorRuntimeSession(scene, serializer=serializer(), fixed_step=0.25)
    preview = EditorPreviewSession(workspace, runtime=runtime)

    assert preview.play_pause() is EditorRuntimeMode.PLAYING
    assert preview.update(99.0)
    assert runtime.runtime_scene.find("Player").x == pytest.approx(4.5)
    assert actor.x == pytest.approx(2.0)

    assert preview.play_pause() is EditorRuntimeMode.PAUSED
    assert preview.step()
    assert runtime.runtime_scene.find("Player").x == pytest.approx(7.0)
    assert preview.stop()
    assert runtime.mode is EditorRuntimeMode.EDIT
    assert actor.x == pytest.approx(2.0)


def test_preview_step_from_edit_mode_creates_isolated_paused_runtime():
    scene = Scene()
    scene.add(MovingActor("Player"))
    workspace = EditorWorkspace(scene)
    runtime = EditorRuntimeSession(scene, serializer=serializer(), fixed_step=0.1)
    preview = EditorPreviewSession(workspace, runtime=runtime)

    assert preview.step()
    assert runtime.mode is EditorRuntimeMode.PAUSED
    assert runtime.frame_count == 1
    assert runtime.runtime_scene.find("Player").x == pytest.approx(1.0)


def test_preview_tracks_workspace_scene_switch_while_in_edit_mode():
    first = Scene()
    workspace = EditorWorkspace(first)
    runtime = EditorRuntimeSession(first, serializer=serializer())
    preview = EditorPreviewSession(workspace, runtime=runtime)
    second = Scene()
    second.add(MovingActor("Second"))

    workspace.switch_scene("second", second)
    preview.update(0.0)

    assert runtime.edit_scene is second
    assert preview.frame().runtime.scene is second


def test_preview_capture_forwards_active_camera_and_mode_to_bridge():
    framebuffer = FakeFramebuffer(bytes(range(12)))
    renderer = FakeRenderer(framebuffer)
    bridge = RendererViewportBridge(renderer)
    scene = Scene()
    workspace = EditorWorkspace(scene)
    preview = EditorPreviewSession(workspace, viewport=bridge)
    camera = object()

    image = preview.capture(2, 2, camera=camera, mode="3d")

    assert image is not None
    assert renderer.mode == "3d"
    assert renderer.rendered[-1] == (scene, camera)


def test_preview_uses_workspace_mode_and_camera_provider_when_capture_is_implicit():
    framebuffer = FakeFramebuffer(bytes(range(12)))
    renderer = FakeRenderer(framebuffer)
    bridge = RendererViewportBridge(renderer)
    scene = Scene()
    workspace = EditorWorkspace(scene)
    workspace.configure_viewport(mode="3d")
    camera = object()
    requested_modes: list[str] = []

    def camera_provider(mode: str) -> object:
        requested_modes.append(mode)
        return camera

    preview = EditorPreviewSession(
        workspace,
        viewport=bridge,
        camera_provider=camera_provider,
    )

    image = preview.capture(2, 2)

    assert image is not None
    assert requested_modes == ["3d"]
    assert renderer.mode == "3d"
    assert renderer.rendered[-1] == (scene, camera)
