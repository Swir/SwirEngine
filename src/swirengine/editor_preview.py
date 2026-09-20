from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .core.scene import Scene
from .editor_runtime import EditorRuntimeFrame, EditorRuntimeMode, EditorRuntimeSession
from .editor_workspace import EditorWorkspace


@dataclass(frozen=True, slots=True)
class EditorViewportImage:
    """RGB framebuffer snapshot ready for desktop editor presentation."""

    width: int
    height: int
    rgb: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("viewport image dimensions must be positive")
        expected = self.width * self.height * 3
        if len(self.rgb) != expected:
            raise ValueError(f"viewport RGB payload must contain exactly {expected} bytes")

    def to_ppm(self) -> bytes:
        header = f"P6\n{self.width} {self.height}\n255\n".encode("ascii")
        return header + self.rgb


@dataclass(frozen=True, slots=True)
class EditorPreviewFrame:
    """Immutable editor-facing snapshot of runtime state plus the latest rendered image."""

    runtime: EditorRuntimeFrame
    image: EditorViewportImage | None


class RendererViewportBridge:
    """Render editor/runtime scenes and read a ModernGL framebuffer back as RGB.

    Explicit framebuffers are bound for the capture and the previously active framebuffer is
    restored afterwards when the backend exposes ``Context.fbo``/``Framebuffer.use``. This keeps
    editor preview captures isolated when the renderer shares a context with another surface.
    """

    def __init__(
        self,
        renderer: Any,
        *,
        camera: object | None = None,
        framebuffer: object | None = None,
    ) -> None:
        required = ("resize", "render")
        missing = [name for name in required if not callable(getattr(renderer, name, None))]
        if missing:
            raise TypeError(f"renderer is missing required methods: {', '.join(missing)}")
        if framebuffer is None:
            ctx = getattr(renderer, "ctx", None)
            framebuffer = None if ctx is None else getattr(ctx, "screen", None)
        if framebuffer is None or not callable(getattr(framebuffer, "read", None)):
            raise TypeError("renderer must expose a readable screen framebuffer")
        self.renderer = renderer
        self.camera = camera
        self.framebuffer = framebuffer

    def capture(
        self,
        scene: Scene,
        width: int,
        height: int,
        *,
        camera: object | None = None,
        mode: str | None = None,
    ) -> EditorViewportImage:
        if not isinstance(scene, Scene):
            raise TypeError("scene must be a Scene")
        width = max(1, int(width))
        height = max(1, int(height))
        if mode is not None:
            normalized_mode = mode.strip().lower()
            if normalized_mode not in {"2d", "3d"}:
                raise ValueError(f"unsupported renderer mode {mode!r}")
            if hasattr(self.renderer, "mode"):
                self.renderer.mode = normalized_mode

        active_camera = self.camera if camera is None else camera
        ctx = getattr(self.renderer, "ctx", None)
        previous_framebuffer = None if ctx is None else getattr(ctx, "fbo", None)
        bind = getattr(self.framebuffer, "use", None)
        if callable(bind):
            bind()
        try:
            self.renderer.resize(width, height)
            self.renderer.render(scene, camera=active_camera)
            rgb = self.framebuffer.read(
                viewport=(0, 0, width, height),
                components=3,
                alignment=1,
            )
        finally:
            if previous_framebuffer is not None and previous_framebuffer is not self.framebuffer:
                restore = getattr(previous_framebuffer, "use", None)
                if callable(restore):
                    restore()

        stride = width * 3
        if len(rgb) != stride * height:
            raise RuntimeError("renderer framebuffer returned an unexpected RGB payload size")
        flipped = b"".join(
            rgb[offset : offset + stride]
            for offset in range((height - 1) * stride, -1, -stride)
        )
        return EditorViewportImage(width, height, flipped)


class EditorPreviewSession:
    """Join an editor workspace, isolated Play/Edit runtime and renderer capture pipeline."""

    def __init__(
        self,
        workspace: EditorWorkspace,
        *,
        runtime: EditorRuntimeSession | None = None,
        viewport: RendererViewportBridge | None = None,
    ) -> None:
        if not isinstance(workspace, EditorWorkspace):
            raise TypeError("workspace must be an EditorWorkspace")
        self.workspace = workspace
        self.runtime = runtime or EditorRuntimeSession(workspace.scene)
        if self.runtime.edit_scene is not workspace.scene:
            raise ValueError("runtime edit scene must match workspace scene")
        self.viewport = viewport
        self._image: EditorViewportImage | None = None

    @property
    def image(self) -> EditorViewportImage | None:
        return self._image

    def frame(self) -> EditorPreviewFrame:
        return EditorPreviewFrame(self.runtime.frame(), self._image)

    def play_pause(self) -> EditorRuntimeMode:
        self._sync_edit_scene()
        if self.runtime.mode is EditorRuntimeMode.PLAYING:
            self.runtime.pause()
        else:
            self.runtime.play()
        return self.runtime.mode

    def stop(self) -> bool:
        stopped = self.runtime.stop()
        self._sync_edit_scene()
        return stopped

    def step(self, dt: float | None = None) -> bool:
        if self.runtime.mode is EditorRuntimeMode.EDIT:
            self._sync_edit_scene()
            self.runtime.play()
            self.runtime.pause()
        elif self.runtime.mode is EditorRuntimeMode.PLAYING:
            self.runtime.pause()
        return self.runtime.step(dt)

    def update(self, dt: float) -> bool:
        self._sync_edit_scene()
        return self.runtime.update(dt)

    def capture(
        self,
        width: int,
        height: int,
        *,
        camera: object | None = None,
        mode: str | None = None,
    ) -> EditorViewportImage | None:
        if self.viewport is None:
            self._image = None
            return None
        self._sync_edit_scene()
        self._image = self.viewport.capture(
            self.runtime.active_scene,
            width,
            height,
            camera=camera,
            mode=mode,
        )
        return self._image

    def _sync_edit_scene(self) -> None:
        if self.runtime.mode is EditorRuntimeMode.EDIT and self.runtime.edit_scene is not self.workspace.scene:
            self.runtime.replace_edit_scene(self.workspace.scene)
