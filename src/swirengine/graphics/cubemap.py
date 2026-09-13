from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


_FACE_NAMES = ("positive_x", "negative_x", "positive_y", "negative_y", "positive_z", "negative_z")


@dataclass(frozen=True, slots=True)
class CubemapFaces:
    """Six image paths in OpenGL cubemap face order (+X, -X, +Y, -Y, +Z, -Z)."""

    positive_x: str | Path
    negative_x: str | Path
    positive_y: str | Path
    negative_y: str | Path
    positive_z: str | Path
    negative_z: str | Path

    def paths(self) -> tuple[Path, Path, Path, Path, Path, Path]:
        return tuple(Path(value).expanduser() for value in self)  # type: ignore[return-value]

    def resolved(self) -> CubemapFaces:
        return CubemapFaces(*(path.resolve() for path in self.paths()))

    def __iter__(self):
        yield self.positive_x
        yield self.negative_x
        yield self.positive_y
        yield self.negative_y
        yield self.positive_z
        yield self.negative_z


@dataclass(frozen=True, slots=True)
class CubemapImageData:
    """Validated RGB cubemap payload ready for a GPU texture-cube upload."""

    width: int
    height: int
    components: int
    faces: tuple[bytes, bytes, bytes, bytes, bytes, bytes]

    @property
    def face_size_bytes(self) -> int:
        return self.width * self.height * self.components

    @property
    def total_size_bytes(self) -> int:
        return self.face_size_bytes * 6


@dataclass(slots=True)
class ImageBasedEnvironment3D:
    """Scene object describing image-based lighting sourced from a cubemap.

    The object is renderer-agnostic: it owns stable creator-facing settings and can be
    inserted directly into ``Scene.objects``. ``load_cubemap_faces`` performs deterministic
    CPU validation/preparation while the renderer can lazily upload the payload to GPU.
    """

    cubemap: CubemapFaces
    intensity: float = 1.0
    diffuse_strength: float = 1.0
    specular_strength: float = 1.0
    max_specular_lod: float = 5.0
    enabled: bool = True
    visible: bool = False
    name: str = "ibl_environment"
    tags: set[str] = field(default_factory=lambda: {"environment", "ibl"})

    def __post_init__(self) -> None:
        self.intensity = _non_negative("intensity", self.intensity)
        self.diffuse_strength = _non_negative("diffuse_strength", self.diffuse_strength)
        self.specular_strength = _non_negative("specular_strength", self.specular_strength)
        self.max_specular_lod = _non_negative("max_specular_lod", self.max_specular_lod)
        self.tags = set(self.tags)
        self.tags.update(("environment", "ibl"))

    def load(self, *, flip_y: bool = False) -> CubemapImageData:
        return load_cubemap_faces(self.cubemap, flip_y=flip_y)


def _non_negative(name: str, value: float) -> float:
    result = float(value)
    if result < 0.0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return result


def load_cubemap_faces(faces: CubemapFaces, *, flip_y: bool = False) -> CubemapImageData:
    """Load six cubemap images as equally-sized RGB byte payloads.

    All faces must exist and have identical dimensions. RGB normalization keeps the GPU
    contract deterministic even when source files use grayscale, palette or alpha modes.
    """

    from PIL import Image

    payloads: list[bytes] = []
    size: tuple[int, int] | None = None
    transpose = Image.Transpose.FLIP_TOP_BOTTOM if flip_y else None

    for face_name, path in zip(_FACE_NAMES, faces.paths(), strict=True):
        if not path.is_file():
            raise FileNotFoundError(f"cubemap {face_name} face does not exist: {path}")
        with Image.open(path) as source:
            image = source.convert("RGB")
            if transpose is not None:
                image = image.transpose(transpose)
            current_size = image.size
            if size is None:
                size = current_size
                if size[0] <= 0 or size[1] <= 0:
                    raise ValueError("cubemap faces must have non-zero dimensions")
            elif current_size != size:
                raise ValueError(
                    "cubemap faces must share identical dimensions; "
                    f"expected {size[0]}x{size[1]}, got {current_size[0]}x{current_size[1]} "
                    f"for {face_name}"
                )
            payloads.append(image.tobytes())

    assert size is not None
    packed = tuple(payloads)
    if len(packed) != 6:
        raise ValueError("cubemap requires exactly six faces")
    return CubemapImageData(
        width=size[0],
        height=size[1],
        components=3,
        faces=packed,  # type: ignore[arg-type]
    )


def cubemap_asset_paths(objects: Iterable[object]) -> tuple[Path, ...]:
    """Return unique cubemap source paths referenced by enabled IBL environments."""

    paths: list[Path] = []
    seen: set[Path] = set()
    for obj in objects:
        if not isinstance(obj, ImageBasedEnvironment3D) or not obj.enabled:
            continue
        for path in obj.cubemap.paths():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return tuple(paths)
