from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from typing_extensions import Self

from ..assets import AssetManager, AssetReloadResult
from .cubemap import ImageBasedEnvironment3D
from .mesh import Mesh3D
from .primitives import Sprite2D

_MATERIAL_TEXTURE_FIELDS = (
    "texture",
    "metallic_roughness_texture",
    "normal_texture",
    "occlusion_texture",
    "emissive_texture",
)


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
    """Connect :class:`AssetManager` live reload to renderer GPU texture caches."""

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

    def bind(self) -> Self:
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
        invalidate_cubemap = getattr(self.renderer, "invalidate_cubemap", None)
        if callable(invalidate_cubemap):
            released = bool(invalidate_cubemap(resolved)) or released
        self._invalidations.append(GPUTextureInvalidation(resolved, released))
        return released

    def watch(self, *assets: str | Path) -> tuple[Path, ...]:
        watched = [self.assets.watch(asset) for asset in assets]
        return tuple(watched)

    def watch_scene_textures(self, scene_or_objects: object) -> tuple[Path, ...]:
        """Watch renderer-visible 2D, material and cubemap texture files."""
        objects = self._objects(scene_or_objects)
        paths: set[Path] = set()
        for obj in objects:
            if isinstance(obj, Sprite2D):
                paths.add(Path(obj.texture).expanduser().resolve())
                continue
            if isinstance(obj, ImageBasedEnvironment3D) and obj.enabled:
                paths.update(path.resolve() for path in obj.cubemap.paths())
                continue
            if not isinstance(obj, Mesh3D) or obj.material is None:
                continue
            material = obj.material
            for field_name in _MATERIAL_TEXTURE_FIELDS:
                texture_path = getattr(material, field_name, None)
                if texture_path is not None:
                    paths.add(Path(texture_path).expanduser().resolve())
        ordered = tuple(sorted(paths, key=lambda item: item.as_posix().lower()))
        for path in ordered:
            self.assets.watcher.watch(path)
        return ordered

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

    def __enter__(self) -> Self:
        return self.bind()

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.unbind()
