from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .graphics.gltf_skeletal import GltfSkeletalAsset, load_gltf_skeletal
from .graphics.skeletal import SkeletalAnimationClip3D, Skeleton3D


@dataclass(frozen=True, slots=True)
class _CachedSkeletalAsset22:
    fingerprint: tuple[int, int]
    asset: GltfSkeletalAsset


class AnimationProjectResourceResolver22:
    """Resolve project-relative creator refs into shipping skeletal runtime resources.

    Supported references are ``path/to/asset.gltf#skeleton`` and
    ``path/to/asset.glb#clip:AnimationName``. Paths are confined to the project root,
    and loaded glTF assets are cached until their size or nanosecond mtime changes.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        loader: Callable[[str | Path], GltfSkeletalAsset] = load_gltf_skeletal,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self._loader = loader
        self._cache: dict[Path, _CachedSkeletalAsset22] = {}

    def __call__(self, resource_ref: str) -> object:
        return self.resolve(resource_ref)

    def resolve(self, resource_ref: str) -> Skeleton3D | SkeletalAnimationClip3D:
        source, fragment = self._parse_ref(resource_ref)
        asset = self._load(source)
        if fragment == "skeleton":
            return self._unique_skeleton(source, asset)
        if fragment.startswith("clip:"):
            name = fragment.removeprefix("clip:").strip()
            if not name:
                raise ValueError("animation clip reference requires a non-empty clip name")
            matches = tuple(clip for clip in asset.clips if clip.name == name)
            if not matches:
                raise KeyError(f"animation clip {name!r} was not found in {source.name}")
            if len(matches) != 1:
                raise ValueError(f"animation clip {name!r} is ambiguous in {source.name}")
            return matches[0]
        raise ValueError(
            "animation resource fragment must be #skeleton or #clip:<AnimationName>"
        )

    def clear_cache(self) -> None:
        self._cache.clear()

    def _parse_ref(self, resource_ref: str) -> tuple[Path, str]:
        if not isinstance(resource_ref, str):
            raise TypeError("animation resource reference must be a string")
        raw_path, separator, fragment = resource_ref.strip().partition("#")
        if not separator or not raw_path or not fragment:
            raise ValueError(
                "animation resource reference must use path.gltf#skeleton or path.gltf#clip:<name>"
            )
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ValueError("animation resource paths must be project-relative")
        source = (self.project_root / relative).resolve()
        try:
            source.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("animation resource path must stay inside the project") from exc
        if source.suffix.casefold() not in {".gltf", ".glb"}:
            raise ValueError("animation resource must reference a .gltf or .glb file")
        if not source.is_file():
            raise FileNotFoundError(f"animation resource not found: {raw_path}")
        return source, fragment.strip()

    def _load(self, source: Path) -> GltfSkeletalAsset:
        stat = source.stat()
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(source)
        if cached is not None and cached.fingerprint == fingerprint:
            return cached.asset
        asset = self._loader(source)
        if not isinstance(asset, GltfSkeletalAsset):
            raise TypeError("skeletal asset loader must return GltfSkeletalAsset")
        self._cache[source] = _CachedSkeletalAsset22(fingerprint, asset)
        return asset

    @staticmethod
    def _unique_skeleton(source: Path, asset: GltfSkeletalAsset) -> Skeleton3D:
        if not asset.objects:
            raise ValueError(f"skeletal asset {source.name} contains no skinned objects")
        skeleton = asset.objects[0].skeleton
        if any(obj.skeleton is not skeleton for obj in asset.objects[1:]):
            raise ValueError(f"skeletal asset {source.name} contains multiple skeletons")
        return skeleton
