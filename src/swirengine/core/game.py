from __future__ import annotations

from collections.abc import Callable
import time
from typing import Literal

from .scene import Scene
from .events import EventBus
from ..input.manager import InputManager


class Game:
    def __init__(self, title: str = "SwirEngine", width: int = 1280, height: int = 720, *, mode: Literal["2d", "3d"] = "2d", vsync: bool = True, target_fps: int = 120, fixed_hz: int = 60) -> None:
        if mode not in ("2d", "3d"):
            raise ValueError("mode must be '2d' or '3d'")
        self.title = title
        self.width = width
        self.height = height
        self.mode = mode
        self.vsync = vsync
        self.target_fps = max(1, target_fps)
        self.fixed_hz = max(1, fixed_hz)
        self.scene = Scene()
        self.events = EventBus()
        self.input = InputManager()
        self.running = False
        self._update_callbacks: list[Callable[[float], None]] = []
        self._fixed_callbacks: list[Callable[[float], None]] = []

    def update(self, callback: Callable[[float], None]) -> Callable[[float], None]:
        self._update_callbacks.append(callback)
        return callback

    def fixed_update(self, callback: Callable[[float], None]) -> Callable[[float], None]:
        self._fixed_callbacks.append(callback)
        return callback

    def stop(self) -> None:
        self.running = False

    def run(self) -> None:
        try:
            import glfw
            import moderngl
        except ImportError as exc:
            raise RuntimeError("Rendering dependencies are missing. Run: pip install -e .") from exc
        if not glfw.init():
            raise RuntimeError("GLFW could not initialize")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        window = glfw.create_window(self.width, self.height, self.title, None, None)
        if window is None:
            glfw.terminate()
            raise RuntimeError("Could not create an OpenGL 3.3 window")
        glfw.make_context_current(window)
        glfw.swap_interval(1 if self.vsync else 0)
        ctx = moderngl.create_context()
        from ..graphics.renderer import Renderer
        renderer = Renderer(ctx, self.width, self.height, self.mode)
        glfw.set_key_callback(window, lambda _w, key, _sc, action, _mods: self.input._on_key(key, action))
        glfw.set_cursor_pos_callback(window, lambda _w, x, y: self.input._on_cursor(float(x), float(y)))
        glfw.set_mouse_button_callback(window, lambda _w, button, action, _mods: self.input._on_button(button, action))
        glfw.set_framebuffer_size_callback(window, lambda _w, w, h: renderer.resize(w, h))
        self.running = True
        last = time.perf_counter()
        accumulator = 0.0
        fixed_dt = 1.0 / self.fixed_hz
        min_frame = 1.0 / self.target_fps
        self.events.emit("start", self)
        try:
            while self.running and not glfw.window_should_close(window):
                frame_start = time.perf_counter()
                now = frame_start
                dt = min(now - last, 0.25)
                last = now
                accumulator += dt
                self.input.begin_frame()
                glfw.poll_events()
                for callback in tuple(self._update_callbacks):
                    callback(dt)
                self.scene.update(dt)
                fixed_steps = 0
                while accumulator >= fixed_dt and fixed_steps < 8:
                    for callback in tuple(self._fixed_callbacks):
                        callback(fixed_dt)
                    accumulator -= fixed_dt
                    fixed_steps += 1
                renderer.render(self.scene)
                glfw.swap_buffers(window)
                self.events.emit("frame", dt)
                if not self.vsync:
                    remaining = min_frame - (time.perf_counter() - frame_start)
                    if remaining > 0:
                        time.sleep(remaining)
        finally:
            self.running = False
            self.events.emit("stop", self)
            glfw.destroy_window(window)
            glfw.terminate()
