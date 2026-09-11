from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..math.types import Color


@dataclass(slots=True)
class Material3D:
    """Simple forward-rendered 3D material.

    ``texture`` may be left unset for a solid-color material. ``tint`` is multiplied
    with the per-instance ``Mesh3D.color`` so existing color workflows remain valid.
    """

    texture: str | Path | None = None
    tint: Color = field(default_factory=Color)
    ambient: float = 0.25
    diffuse: float = 0.75

    def __post_init__(self) -> None:
        self.ambient = max(0.0, float(self.ambient))
        self.diffuse = max(0.0, float(self.diffuse))

    @property
    def textured(self) -> bool:
        return self.texture is not None
