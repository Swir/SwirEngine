from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypeVar

from ..assets import AssetManager
from ..graphics.camera import Camera2D
from ..graphics.primitives import Sprite2D
from ..input.manager import InputManager
from ..physics.collision2d import BoxCollider2D, CollisionWorld2D
from .events import EventBus
from .scene import Scene

T = TypeVar("T")


class Game:
    def __init__(
        self,
        title: str = "SwirEngine",
        width: int = 1280,
        height: int = 720,
        *,
        mode: Literal["2d", "3d"] = "2d",
        vsync: bool = True,
        target_fps: int = 120,
        fixed_hz: int = 60,
        asset_root: str | Path = "assets",
    ) -> None:
        if mode not in ("2d", "3d"):
            raise ValueError("mode must be '2d' or '3d'")
        self.title = title
        self.width = int(width)
        self.height = int(height)
        self.mode = mode
        self.vsync = vsync
        self.target_fps = max(1, int(target_fps))
        self.fixed_hz = max(1, int(fixed_hz))

        self.scene = Scene()
        self.camera = Camera2D()
        self.events = EventBus()
        self.input = InputManager()
        self.assets = AssetManager(asset_root)
        self.collisions = CollisionWorld2D()
        self.running = False

        self._update_callbacks: list[Callable[[float], None]] = []
        self._fixed_callbacks: list[Callable[[float], None]] = []

    def add(self, obj: T) -> T:
        """Add an object to the current scene and return it."""
        return self.scene.add(obj)

    spawn = add

    def add_many(self, *objects: object) -> tuple[object, ...]:
        return self.scene.add_many(*objects)

    def remove(self, obj: object) -> bool:
        removed = self.scene.remove(obj)
        if removed:
            for collider in tuple(self.collisions.colliders):
                if collider.target is obj:
                    self.collisions.remove(collider)
        return removed

    def sprite(self, texture: str | Path, **kwargs: object) -> Sprite2D:
        """Create and add a sprite resolved relative to the game's asset directory."""
        return self.add(Sprite2D(self.assets.resolve(texture), **kwargs))

    def collider(self, target: object, **kwargs: object) -> BoxCollider2D:
        """Create and register a box collider for an existing scene object."""
        return self.collisions.add(BoxCollider2D(target, **kwargs))

    def key(self, name: str) -> bool:
        """Beginner-friendly shorthand for ``game.input.key(name)``."""
        return self.input.key(name)

    def key_pressed(self, name: str) -> bool:
        return self.input.key_pressed(name)

    def key_released(self, name: str) -> bool:
        return self.input.key_released(name)

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
            raise RuntimeError(
                "Missing rendering dependencies. Run: python -m pip install swirengine"
            ) from exc

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

        glfw.set_key_callback(
            window, lambda _w, key, _sc, action, _mods: self.input._on_key(key, action)
        )
        glfw.set_cursor_pos_callback(
            window, lambda _w, x, y: self.input._on_cursor(float(x), float(y))
        )
        glfw.set_mouse_button_callback(
            window, lambda _w, button, action, _mods: self.input._on_button(button, action)
        )
        glfw.set_framebuffer_size_callback(
            window, lambda _w, width, height: renderer.resize(width, height)
        )

        self.running = True
        last = time.perf_counter()
        accumulator = 0.0
        fixed_dt = 1.0 / self.fixed_hz
        min_frame = 1.0 / self.target_fps
        self.events.emit("start", self)

        try:
            while self.running and not glfw.window_should_close(window):
                frame_start = time.perf_counter()
                dt = min(frame_start - last, 0.25)
                last = frame_start
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

                renderer.render(self.scene, camera=self.camera)
                glfw.swap_buffers(window)
                self.events.emit("frame", dt)

                if not self.vsync:
                    remaining = min_frame - (time.perf_counter() - frame_start)
                    if remaining > 0:
                        time.sleep(remaining)
        finally:
            self.running = False
            self.events.emit("stop", self)
            renderer.release()
            glfw.destroy_window(window)
            glfw.terminate()
