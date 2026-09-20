from __future__ import annotations

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
        """Create an isolated headless OpenGL 3.3+ context for editor rendering.

        The live editor viewport is an offscreen framebuffer, so it does not need to own a
        hidden GLFW window. ModernGL's standalone context path is purpose-built for this
        workload and delegates platform context creation to glcontext (WGL on Windows, X11
        on Linux and CGL on macOS). Keeping the editor context windowless avoids coupling
        framebuffer capture to the desktop window system while preserving the engine's
        OpenGL 3.3 renderer baseline.
        """

        try:
            import moderngl
        except ImportError as exc:  # pragma: no cover - package installation failure
            raise EditorRenderBackendUnavailable(
                "live viewport requires the moderngl headless runtime dependencies"
            ) from exc

        ctx: Any = None
        target: ResizableFramebufferTarget | None = None
        renderer: Renderer | None = None
        deactivate: Callable[[], None] | None = None
        try:
            ctx = moderngl.create_standalone_context(require=330)

            def activate() -> None:
                enter = getattr(ctx, "__enter__", None)
                if callable(enter):
                    enter()

            def deactivate_context() -> None:
                exit_context = getattr(ctx, "__exit__", None)
                if callable(exit_context):
                    exit_context(None, None, None)

            deactivate = deactivate_context
            activate()
            target = ResizableFramebufferTarget(ctx, width, height, activate=activate)
            renderer = Renderer(ctx, max(1, int(width)), max(1, int(height)))
            return cls(
                ctx=ctx,
                renderer=renderer,
                target=target,
                deactivate=deactivate,
            )
        except Exception as exc:
            activate_existing = getattr(ctx, "__enter__", None)
            if callable(activate_existing):
                activate_existing()
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
