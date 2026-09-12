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

    def read(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class FakeRenderer:
    def __init__(self, framebuffer: FakeFramebuffer) -> None:
        self.ctx = SimpleNamespace(screen=framebuffer)
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
    assert framebuffer.calls == [
        {"viewport": (0, 0, 2, 2), "components": 3, "alignment": 1}
    ]
    assert image.rgb == top + bottom


def test_renderer_viewport_bridge_rejects_invalid_framebuffer_payload():
    renderer = FakeRenderer(FakeFramebuffer(b"bad"))
    bridge = RendererViewportBridge(renderer)

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
