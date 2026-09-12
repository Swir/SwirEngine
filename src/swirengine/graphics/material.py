from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..math.types import Color


@dataclass(slots=True)
class Material3D:
    """Forward-rendered 3D material with Phong and metallic/roughness controls.

    ``texture`` may be left unset for a solid-color material. ``tint`` is multiplied
    with the per-instance ``Mesh3D.color`` so existing color workflows remain valid.

    Existing Phong materials continue to use ``diffuse``, ``specular`` and ``shininess``
    directly. Setting ``metallic`` and/or ``roughness`` enables the 0.4 PBR bridge: the
    metallic/roughness values are converted into stable Phong-equivalent controls so glTF
    PBR factors affect rendering immediately without breaking the established forward shader.
    A true Cook-Torrance shader remains a later 0.4 renderer milestone.
    """

    texture: str | Path | None = None
    tint: Color = field(default_factory=Color)
    ambient: float = 0.25
    diffuse: float = 0.75
    specular: float = 0.35
    shininess: float = 32.0
    metallic: float | None = None
    roughness: float | None = None

    def __post_init__(self) -> None:
        self.ambient = max(0.0, float(self.ambient))
        self.diffuse = max(0.0, float(self.diffuse))
        self.specular = max(0.0, float(self.specular))
        self.shininess = max(1.0, float(self.shininess))

        if self.metallic is not None or self.roughness is not None:
            metallic = 0.0 if self.metallic is None else float(self.metallic)
            roughness = 0.5 if self.roughness is None else float(self.roughness)
            if not 0.0 <= metallic <= 1.0:
                raise ValueError("metallic must be within 0..1")
            if not 0.0 <= roughness <= 1.0:
                raise ValueError("roughness must be within 0..1")
            self.metallic = metallic
            self.roughness = roughness
            self._apply_pbr_bridge()

    def _apply_pbr_bridge(self) -> None:
        """Map metallic/roughness onto the compatible Phong forward path."""
        metallic = float(self.metallic or 0.0)
        roughness = float(0.5 if self.roughness is None else self.roughness)
        perceptual_roughness = max(0.04, roughness)

        # Metals contribute almost no diffuse reflection; dielectrics retain it.
        self.diffuse *= 1.0 - metallic

        # Approximate dielectric F0=0.04, increasing toward fully metallic reflection.
        self.specular = 0.04 + 0.96 * metallic

        # Convert roughness to a bounded Phong exponent. Squaring twice gives a useful
        # perceptual spread while avoiding pathological highlights near roughness=0.
        alpha = perceptual_roughness * perceptual_roughness
        exponent = (2.0 / max(alpha * alpha, 1e-6)) - 2.0
        self.shininess = min(256.0, max(1.0, exponent))

    @property
    def textured(self) -> bool:
        return self.texture is not None

    @property
    def pbr_enabled(self) -> bool:
        return self.metallic is not None or self.roughness is not None
