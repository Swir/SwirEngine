from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from .editor_preview import RendererViewportBridge
from .graphics.renderer import Renderer


class EditorRenderBackendUnavailable(RuntimeError):
    """Raised when the editor cannot create its isolated OpenGL viewport backend."""


class ResizableFramebufferTarget:
    """ModernGL render target that follows the desktop viewport dimensions.

    The target owns its color/depth attachments and can safely replace them without
    requiring the editor UI to know about ModernGL resource lifetimes. ``owns`` is
    intentionally exposed so :class:`RendererViewportBridge` never restores a stale
    framebuffer that was superseded during a resize.
    """

    def __init__(
        self,
        ctx: Any,
        width: int,
        height: int,
        *,
        activate: Callable[[], None] | None = None,
    ) -> None:
        required = ("texture", "depth_renderbuffer", "framebuffer")
        missing = [name for name in required if not callable(getattr(ctx, name, None))]
        if missing:
            raise TypeError(f"context is missing required methods: {', '.join(missing)}")
        self.ctx = ctx
        self._activate = activate
        self._released = False
        self._retired: list[tuple[object, object, object]] = []
        self.width = 0
        self.height = 0
        self._color: object | None = None
        self._depth: object | None = None
        self._framebuffer: object | None = None
        self.resize(width, height)

    @property
    def framebuffer(self) -> object:
        if self._framebuffer is None or self._released:
            raise RuntimeError("editor framebuffer target is released")
        return self._framebuffer

    def activate(self) -> None:
        if self._released:
            raise RuntimeError("editor framebuffer target is released")
        if self._activate is not None:
            self._activate()

    def owns(self, framebuffer: object) -> bool:
        if framebuffer is self._framebuffer:
            return True
        return any(framebuffer is resources[0] for resources in self._retired)

    def resize(self, width: int, height: int) -> None:
        if self._released:
            raise RuntimeError("editor framebuffer target is released")
        width = max(1, int(width))
        height = max(1, int(height))
        if (width, height) == (self.width, self.height) and self._framebuffer is not None:
            return
        self.activate()
        color = self.ctx.texture((width, height), 4)
        depth = self.ctx.depth_renderbuffer((width, height))
        framebuffer = self.ctx.framebuffer(
            color_attachments=[color],
            depth_attachment=depth,
        )
        if self._framebuffer is not None:
            self._retired.append((self._framebuffer, self._color, self._depth))
        self._framebuffer = framebuffer
        self._color = color
        self._depth = depth
        self.width = width
        self.height = height

    def use(self) -> None:
        self.activate()
        use = getattr(self.framebuffer, "use", None)
        if not callable(use):
            raise TypeError("editor framebuffer does not expose use()")
        use()
        self._release_retired()

    def read(self, **kwargs: Any) -> bytes:
        self.activate()
        read = getattr(self.framebuffer, "read", None)
        if not callable(read):
            raise TypeError("editor framebuffer does not expose read()")
        return bytes(read(**kwargs))

    def release(self) -> None:
        if self._released:
            return
        self.activate()
        current = (self._framebuffer, self._color, self._depth)
        self._framebuffer = None
        self._color = None
        self._depth = None
        self._release_resources(current)
        self._release_retired()
        self._released = True

    def _release_retired(self) -> None:
        retired, self._retired = self._retired, []
        for resources in retired:
            self._release_resources(resources)

    @staticmethod
    def _release_resources(resources: tuple[object | None, object | None, object | None]) -> None:
        for resource in resources:
            release = getattr(resource, "release", None)
            if callable(release):
                release()


class EditorRenderBackend21:
    """Own the isolated GPU context used by SwirEditor 2.1 live viewport captures."""

    def __init__(
        self,
        *,
        ctx: Any,
        renderer: Any,
        target: ResizableFramebufferTarget,
        deactivate: Callable[[], None] | None = None,
        window: object | None = None,
        glfw_module: Any | None = None,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self.target = target
        self._deactivate = deactivate
        self.window = window
        self.glfw = glfw_module
        self.viewport = RendererViewportBridge(renderer, framebuffer=target)
        self._released = False

    @classmethod
    def create(cls, width: int = 640, height: int = 360) -> EditorRenderBackend21:
        """Create an isolated OpenGL 3.3+ context for the offscreen editor viewport.

        Windows and Linux use a hidden GLFW 3.3 core context because that path is reliable
        on desktop drivers and hosted WGL/GLX runners. macOS uses ModernGL's standalone CGL
        context path, avoiding NSGL hidden-window pixel-format failures seen on hosted Apple
        runners. Both paths render into the same resizable offscreen framebuffer and keep the
        SwirEngine renderer on its shared OpenGL 3.3 shader/runtime baseline.
        """

        try:
            import moderngl
        except ImportError as exc:  # pragma: no cover - package installation failure
            raise EditorRenderBackendUnavailable(
                "live viewport requires the moderngl runtime dependency"
            ) from exc

        ctx: Any = None
        target: ResizableFramebufferTarget | None = None
        renderer: Renderer | None = None
        deactivate: Callable[[], None] | None = None
        window: object | None = None
        glfw_module: Any | None = None
        activate: Callable[[], None] | None = None
        try:
            if sys.platform == "darwin":
                ctx = moderngl.create_standalone_context(require=330)

                def activate_standalone() -> None:
                    enter = getattr(ctx, "__enter__", None)
                    if callable(enter):
                        enter()

                def deactivate_standalone() -> None:
                    exit_context = getattr(ctx, "__exit__", None)
                    if callable(exit_context):
                        exit_context(None, None, None)

                activate = activate_standalone
                deactivate = deactivate_standalone
            else:
                try:
                    import glfw
                except ImportError as exc:
                    raise RuntimeError(
                        "live viewport requires the glfw runtime dependency on this platform"
                    ) from exc
                glfw_module = glfw
                if not glfw.init():
                    raise RuntimeError("GLFW initialization failed")
                glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
                glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
                glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
                glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
                if hasattr(glfw, "OPENGL_FORWARD_COMPAT"):
                    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)
                window = glfw.create_window(16, 16, "SwirEditor Renderer", None, None)
                if window is None:
                    raise RuntimeError("cannot create hidden OpenGL 3.3 core window")

                def activate_glfw() -> None:
                    glfw.make_context_current(window)

                activate = activate_glfw

            activate()
            if sys.platform != "darwin":
                ctx = moderngl.create_context(require=330)
            target = ResizableFramebufferTarget(ctx, width, height, activate=activate)
            renderer = Renderer(ctx, max(1, int(width)), max(1, int(height)))
            return cls(
                ctx=ctx,
                renderer=renderer,
                target=target,
                deactivate=deactivate,
                window=window,
                glfw_module=glfw_module,
            )
        except Exception as exc:
            if renderer is not None:
                release = getattr(renderer, "release", None)
                if callable(release):
                    release()
            if target is not None:
                target.release()
            if deactivate is not None:
                deactivate()
            release_ctx = getattr(ctx, "release", None)
            if callable(release_ctx):
                release_ctx()
            if glfw_module is not None and window is not None:
                glfw_module.destroy_window(window)
            raise EditorRenderBackendUnavailable(
                f"cannot initialize live SwirEditor viewport: {exc}"
            ) from exc

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self.target.activate()
        release_renderer = getattr(self.renderer, "release", None)
        if callable(release_renderer):
            release_renderer()
        self.target.release()
        if self._deactivate is not None:
            self._deactivate()
        release_ctx = getattr(self.ctx, "release", None)
        if callable(release_ctx):
            release_ctx()
        if self.glfw is not None and self.window is not None:
            self.glfw.destroy_window(self.window)
