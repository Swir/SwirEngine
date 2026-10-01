from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .core.game import Game
from .core.scene import Scene
from .editor_preview import EditorViewportImage, RendererViewportBridge
from .editor_render_backend21 import EditorRenderBackend21
from .graphics.csm_renderer import Renderer2
from .graphics.postprocess import PostProcessRenderer
from .lighting_authoring22 import (
    EditorLightingError22,
    EditorLightingTooling22,
    LightSpec22,
    SceneLightingSpec22,
    _contained,
)
from .serialization import SceneSerializer

MAX_LIGHTING_PREVIEW_DIMENSION = 1024
MAX_LIGHTING_PREVIEW_OBJECTS = 4096
MAX_LIGHTING_PREVIEW_SCENE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LightingSceneSource22:
    key: str
    mode: str
    scene: Scene
    camera: object
    serializer: SceneSerializer


def _asset_signature(tooling: EditorLightingTooling22, spec: SceneLightingSpec22) -> tuple:
    texture = spec.environment.skybox_texture
    if texture is None:
        return ()
    assets = _contained(tooling.project_root, "assets")
    target = _contained(assets, texture)
    if not target.is_file():
        raise EditorLightingError22(f"missing skybox texture: {texture}")
    info = target.stat()
    return (str(target), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _PreviewContext:
    """Keep the production renderer's resolve on its own resizable framebuffer."""

    def __init__(self, backend: EditorRenderBackend21) -> None:
        object.__setattr__(self, "_backend", backend)

    @property
    def screen(self) -> object:
        return self._backend.target.framebuffer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend.ctx, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._backend.ctx, name, value)


class LightingScenePreview22:
    """Isolated scene snapshot and owned production renderer; never run game scripts."""

    def __init__(
        self, tooling: EditorLightingTooling22, source: LightingSceneSource22,
        *, backend_factory: Callable[..., EditorRenderBackend21] = EditorRenderBackend21.create,
    ) -> None:
        if len(source.scene.objects) + len(source.scene.entities) > MAX_LIGHTING_PREVIEW_OBJECTS:
            raise EditorLightingError22("lighting preview scene exceeds object budget")
        snapshot = source.serializer.dumps_scene(source.scene, indent=None)
        if len(snapshot.encode("utf-8")) > MAX_LIGHTING_PREVIEW_SCENE_BYTES:
            raise EditorLightingError22("lighting preview scene exceeds snapshot byte budget")
        self.runtime = tooling.build_runtime(source.key)
        if self.runtime.spec.mode != source.mode:
            raise EditorLightingError22("lighting profile mode does not match active scene")
        self.game = Game(mode=source.mode)
        self.game.scene = source.serializer.loads_scene(snapshot)
        self.mount = self.runtime.apply_to_game(self.game)
        self._backend_factory = backend_factory
        self._backend: EditorRenderBackend21 | None = None
        self._closed = False
        self.frames = 0

    def capture(self, width: int, height: int, camera: object) -> EditorViewportImage:
        if self._closed:
            raise EditorLightingError22("lighting preview is closed")
        for value in (width, height):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise EditorLightingError22("preview dimensions must be positive integers")
        width, height = (min(value, MAX_LIGHTING_PREVIEW_DIMENSION) for value in (width, height))
        if self._backend is None:
            backend = self._backend_factory(width, height)
            try:
                backend.target.activate()
                ctx = _PreviewContext(backend)
                renderer = (
                    Renderer2(ctx, width, height, self.game.mode, postprocess=self.game.postprocess,
                              renderer2=self.game.renderer2_settings)
                    if self.game.mode == "3d" else
                    PostProcessRenderer(ctx, width, height, self.game.mode,
                                        postprocess=self.game.postprocess)
                )
                previous = backend.renderer
                backend.renderer = renderer
                backend.viewport = RendererViewportBridge(renderer, framebuffer=backend.target)
                previous.release()
            except Exception:
                backend.release()
                raise
            self._backend = backend
        active_camera = copy.deepcopy(camera)
        if self.runtime.skybox is not None:
            self.runtime.skybox.follow(active_camera)
        result = self._backend.viewport.capture(
            self.game.scene, width, height, camera=active_camera, mode=self.game.mode,
        )
        self.frames += 1
        return result

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._backend is not None:
                self._backend.release()
        finally:
            self._backend = None
            self.mount.unmount()


class EditorLightingPanelController22:
    """Active-scene creator controls with preview isolation and fail-closed lifecycle."""

    def __init__(
        self, tooling: EditorLightingTooling22, source: Callable[[], LightingSceneSource22],
        *, preview_factory: Callable[..., LightingScenePreview22] = LightingScenePreview22,
    ) -> None:
        self.tooling = tooling
        self.source = source
        self._preview_factory = preview_factory
        self._preview: LightingScenePreview22 | None = None
        self._signature: tuple | None = None
        self._binding: tuple[str, int, str] | None = None
        self.running = False
        self.image: EditorViewportImage | None = None
        self.status = "Lighting editor ready; preview uses an isolated scene snapshot"

    @property
    def active(self) -> bool:
        return self._preview is not None

    def spec(self) -> SceneLightingSpec22:
        source = self.source()
        for spec in self.tooling.profiles():
            if spec.scene == source.key:
                if spec.mode != source.mode:
                    raise EditorLightingError22("lighting profile mode does not match active scene")
                return spec
        return SceneLightingSpec22(source.key, mode=source.mode)

    def ensure_profile(self) -> SceneLightingSpec22:
        return self.tooling.set_profile(self.spec())

    def update_section(self, section: str, **changes: Any) -> SceneLightingSpec22:
        if section not in {"environment", "postfx", "renderer"}:
            raise EditorLightingError22("unknown lighting section")
        current = self.spec()
        candidate = replace(current, **{section: replace(getattr(current, section), **changes)})
        self.tooling.set_profile(candidate)
        self.status = f"Updated {section} for {current.scene}"
        return candidate

    def set_light(self, light: LightSpec22) -> SceneLightingSpec22:
        if not isinstance(light, LightSpec22):
            raise EditorLightingError22("expected a validated light")
        spec = self.spec()
        lights = tuple(item for item in spec.lights if item.name != light.name) + (light,)
        updated = self.tooling.set_profile(replace(spec, lights=lights))
        self.status = f"Updated light {light.name}"
        return updated

    def remove_light(self, name: str) -> SceneLightingSpec22:
        spec = self.spec()
        if not any(light.name == name for light in spec.lights):
            raise EditorLightingError22(f"unknown light {name!r}")
        updated = self.tooling.set_profile(replace(
            spec, lights=tuple(light for light in spec.lights if light.name != name),
        ))
        self.status = f"Removed light {name}"
        return updated

    def save(self) -> None:
        self.tooling.save()
        self.status = "Saved scene lighting profiles"

    def sync_scene(self) -> bool:
        source = self.source()
        binding = (source.key, id(source.scene), source.mode)
        if self._binding is not None and self._binding != binding:
            self.stop()
            self.status = "Active scene changed; start a new lighting preview"
            return False
        return True

    def start(self) -> None:
        self.stop()
        source = self.source()
        spec = self.ensure_profile()
        try:
            signature = (spec.fingerprint, _asset_signature(self.tooling, spec))
            self._preview = self._preview_factory(self.tooling, source)
        except Exception as exc:
            self.status = f"Lighting preview blocked: {exc}"
            raise
        self._signature = signature
        self._binding = (source.key, id(source.scene), source.mode)
        self.running = True
        self.status = "Live lighting preview; original scene and renderer stay unchanged"

    def pause(self) -> None:
        self.running = False
        self.status = "Lighting preview paused"

    def stop(self) -> None:
        preview, self._preview = self._preview, None
        self.running = False
        self.image = None
        self._signature = self._binding = None
        self.status = "Lighting preview stopped; original scene unchanged"
        if preview is not None:
            preview.close()

    def capture(self, width: int = 640, height: int = 360, *, step: bool = False) -> EditorViewportImage | None:
        try:
            if not self.sync_scene() or self._preview is None:
                return None
            spec = self.spec()
            signature = (spec.fingerprint, _asset_signature(self.tooling, spec))
            if signature != self._signature:
                was_running = self.running
                self.start()
                self.running = was_running
            if not self.running and not step:
                return self.image
            assert self._preview is not None
            self.image = self._preview.capture(width, height, self.source().camera)
            self.status = f"{spec.scene} | {spec.mode.upper()} | {self._preview.frames} rendered frames"
            return self.image
        except Exception as exc:
            self.stop()
            self.status = f"Lighting preview stopped: {exc}"
            raise
