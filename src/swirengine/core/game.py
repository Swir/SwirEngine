from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypeVar

from ..assets import AssetManager
from ..audio import AudioEngine, AudioHandle
from ..debug import DebugOverlay
from ..graphics.camera import Camera2D
from ..graphics.camera3d import Camera3D
from ..graphics.gltf import load_gltf
from ..graphics.lights import DirectionalLight3D, PointLight3D, SpotLight3D
from ..graphics.mesh import Mesh3D, MeshData
from ..graphics.obj import load_obj
from ..graphics.postprocess import PostProcessRenderer, PostProcessSettings
from ..graphics.primitives import Sprite2D, Text2D
from ..input.manager import InputManager
from ..particles import ParticleEmitter2D
from ..physics.collision2d import BoxCollider2D, CollisionWorld2D
from ..physics.rigidbody2d import PhysicsWorld2D, RigidBody2D
from ..profiler import Profiler
from ..storage import SaveStore
from ..tilemap import TileMap2D
from ..ui import UIButton, UILabel, UIManager, UIPanel, UIProgressBar
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
        save_path: str | Path | None = None,
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
        self.camera: Camera2D | Camera3D = Camera3D() if mode == "3d" else Camera2D()
        self.events = EventBus()
        self.input = InputManager()
        self.assets = AssetManager(asset_root)
        self.audio = AudioEngine(self.assets)
        self.collisions = CollisionWorld2D()
        self.physics = PhysicsWorld2D(self.collisions)
        self.storage = SaveStore(save_path or "save.json", autoload=save_path is not None)
        self.ui = UIManager(self.scene)
        self.profiler = Profiler()
        self.debug_overlay = DebugOverlay(self.scene, self.profiler)
        self.postprocess = PostProcessSettings()
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
        if self.ui.remove(obj):
            return True
        if isinstance(obj, (TileMap2D, ParticleEmitter2D)):
            for child in obj.children:
                self.scene.remove(child)

        removed = self.scene.remove(obj)
        if removed:
            for collider in tuple(self.collisions.colliders):
                if collider.target is obj:
                    self.collisions.remove(collider)
            for body in tuple(self.physics.bodies):
                if body.target is obj:
                    self.physics.remove(body)
        return removed

    def sprite(self, texture: str | Path, **kwargs: object) -> Sprite2D:
        """Create and add a sprite resolved relative to the game's asset directory."""
        return self.add(Sprite2D(self.assets.resolve(texture), **kwargs))

    def text(self, value: str, x: float = 0.0, y: float = 0.0, **kwargs: object) -> Text2D:
        """Create world-space text rendered through the shared 2D texture pipeline."""
        return self.add(Text2D(value, x, y, **kwargs))

    def mesh(self, data: MeshData, **kwargs: object) -> Mesh3D:
        """Create and add a 3D mesh instance from CPU-side mesh data."""
        if self.mode != "3d":
            raise RuntimeError("Game.mesh(...) requires mode='3d'")
        return self.add(Mesh3D(data, **kwargs))

    def obj(self, asset: str | Path, **kwargs: object) -> Mesh3D:
        """Load a Wavefront OBJ from the asset root and add it as a Mesh3D."""
        if self.mode != "3d":
            raise RuntimeError("Game.obj(...) requires mode='3d'")
        return self.mesh(load_obj(self.assets.require(asset)), **kwargs)

    def gltf(self, asset: str | Path, *, mesh_index: int = 0, **kwargs: object) -> Mesh3D:
        """Load a static glTF 2.0 mesh from the asset root and add it as a Mesh3D."""
        if self.mode != "3d":
            raise RuntimeError("Game.gltf(...) requires mode='3d'")
        return self.mesh(load_gltf(self.assets.require(asset), mesh_index=mesh_index), **kwargs)

    def directional_light(self, **kwargs: object) -> DirectionalLight3D:
        """Create a sun/moon-style directional light in a 3D game."""
        if self.mode != "3d":
            raise RuntimeError("Game.directional_light(...) requires mode='3d'")
        return self.add(DirectionalLight3D(**kwargs))

    def point_light(self, **kwargs: object) -> PointLight3D:
        """Create an omnidirectional point light in a 3D game."""
        if self.mode != "3d":
            raise RuntimeError("Game.point_light(...) requires mode='3d'")
        return self.add(PointLight3D(**kwargs))

    def spot_light(self, **kwargs: object) -> SpotLight3D:
        """Create a cone-shaped spot light in a 3D game."""
        if self.mode != "3d":
            raise RuntimeError("Game.spot_light(...) requires mode='3d'")
        return self.add(SpotLight3D(**kwargs))

    def label(self, value: str, x: float = 0.0, y: float = 0.0, **kwargs: object) -> UILabel:
        return self.ui.label(value, x, y, **kwargs)

    def panel(self, x: float, y: float, width: float, height: float, **kwargs: object) -> UIPanel:
        return self.ui.panel(x, y, width, height, **kwargs)

    def button(
        self,
        value: str,
        x: float,
        y: float,
        width: float = 220.0,
        height: float = 56.0,
        **kwargs: object,
    ) -> UIButton:
        return self.ui.button(value, x, y, width, height, **kwargs)

    def progress_bar(
        self,
        x: float,
        y: float,
        width: float = 260.0,
        height: float = 24.0,
        **kwargs: object,
    ) -> UIProgressBar:
        return self.ui.progress_bar(x, y, width, height, **kwargs)

    def tilemap(
        self,
        texture: str | Path,
        width: int,
        height: int,
        tile_width: float,
        tile_height: float,
        atlas_columns: int,
        atlas_rows: int,
        **kwargs: object,
    ) -> TileMap2D:
        """Create a tilemap and register its pooled sprites with the current scene."""
        tilemap = TileMap2D(
            self.assets.resolve(texture),
            width,
            height,
            tile_width,
            tile_height,
            atlas_columns,
            atlas_rows,
            **kwargs,
        )
        self.add(tilemap)
        self.add_many(*tilemap.children)
        return tilemap

    def particles(self, x: float = 0.0, y: float = 0.0, **kwargs: object) -> ParticleEmitter2D:
        """Create a pooled particle emitter and register its visuals with the scene."""
        emitter = ParticleEmitter2D(x, y, **kwargs)
        self.add(emitter)
        self.add_many(*emitter.children)
        return emitter

    def collider(self, target: object, **kwargs: object) -> BoxCollider2D:
        """Create and register a box collider for an existing scene object."""
        return self.collisions.add(BoxCollider2D(target, **kwargs))

    def rigidbody(
        self,
        target: object,
        *,
        collider: BoxCollider2D | None = None,
        **kwargs: object,
    ) -> RigidBody2D:
        """Create a rigid body, reusing the target's registered collider when possible."""
        if collider is None:
            collider = next(
                (item for item in self.collisions.colliders if item.target is target),
                None,
            )
        if collider is None:
            collider = self.collider(target)
        elif not any(item is collider for item in self.collisions.colliders):
            self.collisions.add(collider)
        return self.physics.add(RigidBody2D(target, collider, **kwargs))

    def sound(self, asset: str | Path, *, volume: float = 1.0, loop: bool = False) -> AudioHandle:
        """Play a sound effect through the game's audio service."""
        return self.audio.play(asset, volume=volume, loop=loop)

    def music(self, asset: str | Path, *, volume: float = 1.0, loop: bool = True) -> AudioHandle:
        """Play background music, replacing the previous music track."""
        return self.audio.music(asset, volume=volume, loop=loop)

    def show_debug(self, enabled: bool = True) -> DebugOverlay:
        """Show or hide the built-in FPS/timing/render-statistics overlay."""
        return self.debug_overlay.set_enabled(enabled)

    def configure_postprocess(self, **settings: object) -> PostProcessSettings:
        """Configure the optional GPU full-screen post-processing pass."""
        return self.postprocess.update(**settings)

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
        renderer = PostProcessRenderer(
            ctx,
            self.width,
            self.height,
            self.mode,
            postprocess=self.postprocess,
        )

        glfw.set_key_callback(
            window, lambda _w, key, _sc, action, _mods: self.input._on_key(key, action)
        )
        glfw.set_cursor_pos_callback(
            window, lambda _w, x, y: self.input._on_cursor(float(x), float(y))
        )
        glfw.set_mouse_button_callback(
            window, lambda _w, button, action, _mods: self.input._on_button(button, action)
        )

        def on_resize(_window, width: int, height: int) -> None:
            self.width = max(1, int(width))
            self.height = max(1, int(height))
            renderer.resize(self.width, self.height)

        glfw.set_framebuffer_size_callback(window, on_resize)

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
                self.profiler.begin_frame()

                with self.profiler.measure("update"):
                    self.input.begin_frame()
                    glfw.poll_events()
                    self.ui.update(self.input, self.width, self.height)

                    for callback in tuple(self._update_callbacks):
                        callback(dt)
                    self.scene.update(dt)

                with self.profiler.measure("physics"):
                    fixed_steps = 0
                    while accumulator >= fixed_dt and fixed_steps < 8:
                        for callback in tuple(self._fixed_callbacks):
                            callback(fixed_dt)
                        self.physics.step(fixed_dt)
                        accumulator -= fixed_dt
                        fixed_steps += 1

                with self.profiler.measure("render"):
                    renderer.render(self.scene, camera=self.camera)
                    glfw.swap_buffers(window)

                self.profiler.end_frame(dt, renderer.stats)
                self.debug_overlay.update(dt, self.width, self.height)
                self.events.emit("frame", dt)

                if not self.vsync:
                    remaining = min_frame - (time.perf_counter() - frame_start)
                    if remaining > 0:
                        time.sleep(remaining)
        finally:
            self.running = False
            self.events.emit("stop", self)
            self.audio.shutdown()
            renderer.release()
            glfw.destroy_window(window)
            glfw.terminate()
