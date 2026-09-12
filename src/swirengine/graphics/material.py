from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..math.types import Color


@dataclass(slots=True)
class Material3D:
    """Forward-rendered 3D material with legacy Phong and native PBR controls.

    ``texture`` may be left unset for a solid-color material. ``tint`` is multiplied
    with the per-instance ``Mesh3D.color`` so existing color workflows remain valid.

    Materials that omit metallic/roughness continue to use the legacy Phong path.
    Supplying ``metallic``/``roughness`` enables Cook-Torrance metallic/roughness shading.
    ``metallic_roughness_texture`` follows glTF 2.0 channel packing: roughness is read from
    green and metallic from blue, then multiplied by the scalar factors.

    The historical Phong bridge is intentionally retained on the CPU-side fields for API
    compatibility with 0.4.7-0.4.9 code that inspects ``diffuse``, ``specular`` or
    ``shininess``. The renderer ignores those bridge values while native PBR is active.
    """

    texture: str | Path | None = None
    tint: Color = field(default_factory=Color)
    ambient: float = 0.25
    diffuse: float = 0.75
    specular: float = 0.35
    shininess: float = 32.0
    metallic: float | None = None
    roughness: float | None = None
    metallic_roughness_texture: str | Path | None = None

    def __post_init__(self) -> None:
        self.ambient = max(0.0, float(self.ambient))
        self.diffuse = max(0.0, float(self.diffuse))
        self.specular = max(0.0, float(self.specular))
        self.shininess = max(1.0, float(self.shininess))

        pbr_requested = (
            self.metallic is not None
            or self.roughness is not None
            or self.metallic_roughness_texture is not None
        )
        if pbr_requested:
            metallic = 1.0 if self.metallic is None and self.metallic_roughness_texture else (
                0.0 if self.metallic is None else float(self.metallic)
            )
            roughness = 1.0 if self.roughness is None and self.metallic_roughness_texture else (
                0.5 if self.roughness is None else float(self.roughness)
            )
            if not 0.0 <= metallic <= 1.0:
                raise ValueError("metallic must be within 0..1")
            if not 0.0 <= roughness <= 1.0:
                raise ValueError("roughness must be within 0..1")
            self.metallic = metallic
            self.roughness = roughness
            self._apply_pbr_bridge()

    def _apply_pbr_bridge(self) -> None:
        """Preserve the 0.4.7-0.4.9 public Phong-field compatibility mapping."""
        metallic = float(self.metallic or 0.0)
        roughness = float(0.5 if self.roughness is None else self.roughness)
        perceptual_roughness = max(0.04, roughness)

        self.diffuse *= 1.0 - metallic
        self.specular = 0.04 + 0.96 * metallic

        alpha = perceptual_roughness * perceptual_roughness
        exponent = (2.0 / max(alpha * alpha, 1e-6)) - 2.0
        self.shininess = min(256.0, max(1.0, exponent))

    @property
    def textured(self) -> bool:
        return self.texture is not None

    @property
    def pbr_enabled(self) -> bool:
        return (
            self.metallic is not None
            or self.roughness is not None
            or self.metallic_roughness_texture is not None
        )
