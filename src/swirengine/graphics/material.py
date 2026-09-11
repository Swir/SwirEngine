from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..math.types import Color


@dataclass(slots=True)
class Material3D:
    """Forward-rendered 3D material with classic Phong controls.

    ``texture`` may be left unset for a solid-color material. ``tint`` is multiplied
    with the per-instance ``Mesh3D.color`` so existing color workflows remain valid.
    ``specular`` controls highlight strength while ``shininess`` controls highlight size.
    """

    texture: str | Path | None = None
    tint: Color = field(default_factory=Color)
    ambient: float = 0.25
    diffuse: float = 0.75
    specular: float = 0.35
    shininess: float = 32.0

    def __post_init__(self) -> None:
        self.ambient = max(0.0, float(self.ambient))
        self.diffuse = max(0.0, float(self.diffuse))
        self.specular = max(0.0, float(self.specular))
        self.shininess = max(1.0, float(self.shininess))

    @property
    def textured(self) -> bool:
        return self.texture is not None
