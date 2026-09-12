from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..assets import AssetManager, AssetReloadResult
from .mesh import Mesh3D
from .primitives import Sprite2D


class _ReleasableTexture(Protocol):
    def release(self) -> None: ...


class _RendererTextureCache(Protocol):
    _textures: dict[str, tuple[_ReleasableTexture, int, int]]


@dataclass(frozen=True, slots=True)
class GPUTextureInvalidation:
    """One renderer texture-cache invalidation caused by an asset change."""

    path: Path
    released: bool


class RendererAssetBridge:
    """Connect :class:`AssetManager` live reload to the renderer GPU texture cache.

    The bridge deliberately lives in the graphics package instead of ``AssetManager`` so the
    generic asset layer stays independent from OpenGL/ModernGL. It can be polled from an editor
    or game update loop and owns no background threads.
    """

    def __init__(self, renderer: _RendererTextureCache, assets: AssetManager) -> None:
        self.renderer = renderer
        self.assets = assets
        self._bound = False
        self._invalidations: list[GPUTextureInvalidation] = []

    @property
    def bound(self) -> bool:
        return self._bound

    @property
    def invalidations(self) -> tuple[GPUTextureInvalidation, ...]:
        return tuple(self._invalidations)

    def bind(self) -> RendererAssetBridge:
        if not self._bound:
            self.assets.add_invalidator(self.invalidate_texture)
            self._bound = True
        return self

    def unbind(self) -> bool:
        if not self._bound:
            return False
        self.assets.remove_invalidator(self.invalidate_texture)
        self._bound = False
        return True

    def clear_history(self) -> None:
        self._invalidations.clear()

    def invalidate_texture(self, path: str | Path) -> bool:
        resolved = Path(path).expanduser().resolve()
        key = str(resolved)
        cached = self.renderer._textures.pop(key, None)
        released = cached is not None
        if cached is not None:
            texture, _, _ = cached
            texture.release()
        self._invalidations.append(GPUTextureInvalidation(resolved, released))
        return released

    def watch(self, *assets: str | Path) -> tuple[Path, ...]:
        watched = [self.assets.watch(asset) for asset in assets]
        return tuple(watched)

    def watch_scene_textures(self, scene_or_objects: object) -> tuple[Path, ...]:
        """Watch renderer-visible texture files from a scene or arbitrary object iterable."""
        objects = self._objects(scene_or_objects)
        paths: set[Path] = set()
        for obj in objects:
            if isinstance(obj, Sprite2D):
                paths.add(Path(obj.texture).expanduser().resolve())
                continue
            if not isinstance(obj, Mesh3D) or obj.material is None:
                continue
            material = obj.material
            if material.texture is not None:
                paths.add(Path(material.texture).expanduser().resolve())
            if material.metallic_roughness_texture is not None:
                paths.add(Path(material.metallic_roughness_texture).expanduser().resolve())
        for path in sorted(paths, key=lambda item: item.as_posix().lower()):
            self.assets.watcher.watch(path)
        return tuple(sorted(paths, key=lambda item: item.as_posix().lower()))

    def poll(
        self,
        *,
        scene_or_objects: object | None = None,
        reload_cached: bool = True,
    ) -> tuple[AssetReloadResult, ...]:
        """Optionally sync scene texture watches, then process live asset changes."""
        if scene_or_objects is not None:
            self.watch_scene_textures(scene_or_objects)
        return self.assets.poll_changes(reload_cached=reload_cached)

    @staticmethod
    def _objects(scene_or_objects: object) -> Iterable[object]:
        objects = getattr(scene_or_objects, "objects", scene_or_objects)
        if isinstance(objects, Iterable):
            return objects
        raise TypeError("scene_or_objects must expose .objects or be iterable")

    def __enter__(self) -> RendererAssetBridge:
        return self.bind()

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.unbind()
