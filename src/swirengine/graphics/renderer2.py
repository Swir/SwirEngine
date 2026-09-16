from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from ..math.types import Color, Vec3
from .camera3d import Camera3D
from .lights import DirectionalLight3D, select_lights
from .mesh import Mesh3D
from .primitives import Cube3D

Renderer2PassName = Literal[
    "depth_prepass",
    "shadow_cascades",
    "opaque",
    "decals",
    "ssao",
    "bloom_extract",
    "bloom_downsample",
    "bloom_upsample",
    "hdr_resolve",
]


@dataclass(frozen=True, slots=True)
class Renderer2Settings:
    """Creator-facing quality controls for the additive SwirEngine 1.4 renderer path.

    The settings intentionally describe rendering work without requiring a GPU context. This keeps
    cascade layout, pass scheduling and performance budgets deterministic and testable before the
    OpenGL backend allocates textures or submits draws.
    """

    cascaded_shadows: bool = True
    shadow_cascades: int = 4
    shadow_resolution: int = 2048
    shadow_distance: float = 120.0
    shadow_split_lambda: float = 0.72
    shadow_overlap: float = 0.08
    depth_prepass: bool = True
    ssao: bool = True
    ssao_radius: float = 0.7
    ssao_power: float = 1.35
    ssao_samples: int = 16
    bloom: bool = True
    bloom_threshold: float = 1.05
    bloom_intensity: float = 0.08
    bloom_levels: int = 5
    decals: bool = True
    max_decals: int = 256
    hdr: bool = True

    def __post_init__(self) -> None:
        if not 1 <= int(self.shadow_cascades) <= 4:
            raise ValueError("shadow_cascades must be between 1 and 4")
        if int(self.shadow_resolution) < 128:
            raise ValueError("shadow_resolution must be at least 128")
        if float(self.shadow_distance) <= 0.0:
            raise ValueError("shadow_distance must be greater than zero")
        if not 0.0 <= float(self.shadow_split_lambda) <= 1.0:
            raise ValueError("shadow_split_lambda must be between 0 and 1")
        if not 0.0 <= float(self.shadow_overlap) < 0.5:
            raise ValueError("shadow_overlap must be in [0, 0.5)")
        if float(self.ssao_radius) <= 0.0:
            raise ValueError("ssao_radius must be greater than zero")
        if float(self.ssao_power) <= 0.0:
            raise ValueError("ssao_power must be greater than zero")
        if int(self.ssao_samples) not in {8, 16, 32, 64}:
            raise ValueError("ssao_samples must be one of 8, 16, 32, 64")
        if float(self.bloom_threshold) < 0.0 or float(self.bloom_intensity) < 0.0:
            raise ValueError("bloom threshold/intensity must be non-negative")
        if not 1 <= int(self.bloom_levels) <= 8:
            raise ValueError("bloom_levels must be between 1 and 8")
        if int(self.max_decals) < 0:
            raise ValueError("max_decals must be non-negative")


@dataclass(frozen=True, slots=True)
class ShadowCascade3D:
    """One camera-space CSM interval and a stable world-space focus volume."""

    index: int
    near: float
    far: float
    blend_start: float
    focus: Vec3
    extent: float
    texel_world_size: float

    def contains_depth(self, depth: float) -> bool:
        return self.near <= float(depth) <= self.far


@dataclass(frozen=True, slots=True)
class CascadedShadowPlan3D:
    near: float
    far: float
    cascades: tuple[ShadowCascade3D, ...]

    @property
    def split_depths(self) -> tuple[float, ...]:
        return tuple(cascade.far for cascade in self.cascades)

    def cascade_for_depth(self, depth: float) -> ShadowCascade3D:
        value = max(self.near, float(depth))
        for cascade in self.cascades:
            if value <= cascade.far:
                return cascade
        return self.cascades[-1]


@dataclass(slots=True)
class Decal3D:
    """A bounded world-space decal volume consumed by the Renderer 2.0 decal pass."""

    position: Vec3 = field(default_factory=Vec3)
    size: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    color: Color = field(default_factory=Color)
    opacity: float = 1.0
    layer: int = 0
    enabled: bool = True
    visible: bool = True
    texture: str | None = None

    def __post_init__(self) -> None:
        if min(float(self.size.x), float(self.size.y), float(self.size.z)) <= 0.0:
            raise ValueError("decal size components must be greater than zero")
        if not 0.0 <= float(self.opacity) <= 1.0:
            raise ValueError("decal opacity must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Renderer2FramePass:
    name: Renderer2PassName
    submissions: int = 0
    draw_calls: int = 0


@dataclass(frozen=True, slots=True)
class Renderer2Diagnostics:
    frame_passes: int = 0
    visible_opaque: int = 0
    depth_prepass_draws: int = 0
    shadow_cascades: int = 0
    shadow_draws: int = 0
    decal_candidates: int = 0
    decals_submitted: int = 0
    decals_dropped: int = 0
    ssao_passes: int = 0
    bloom_passes: int = 0
    hdr_resolves: int = 0
    estimated_draw_calls: int = 0


@dataclass(frozen=True, slots=True)
class Renderer2FramePlan:
    passes: tuple[Renderer2FramePass, ...]
    cascades: CascadedShadowPlan3D | None
    decals: tuple[Decal3D, ...]
    diagnostics: Renderer2Diagnostics

    def has_pass(self, name: Renderer2PassName) -> bool:
        return any(item.name == name for item in self.passes)



def practical_cascade_splits(
    near: float,
    far: float,
    count: int,
    split_lambda: float,
) -> tuple[float, ...]:
    """Return monotonic practical CSM splits (uniform/logarithmic blend).

    ``split_lambda=0`` is fully uniform and ``1`` is fully logarithmic. The final split is forced to
    ``far`` so floating-point drift cannot leave an uncovered tail.
    """

    near_value = float(near)
    far_value = float(far)
    cascade_count = int(count)
    blend = float(split_lambda)
    if near_value <= 0.0 or far_value <= near_value:
        raise ValueError("cascade planes must satisfy 0 < near < far")
    if not 1 <= cascade_count <= 4:
        raise ValueError("cascade count must be between 1 and 4")
    if not 0.0 <= blend <= 1.0:
        raise ValueError("split_lambda must be between 0 and 1")

    ratio = far_value / near_value
    splits: list[float] = []
    for index in range(1, cascade_count + 1):
        progress = index / cascade_count
        uniform = near_value + (far_value - near_value) * progress
        logarithmic = near_value * ratio**progress
        split = uniform * (1.0 - blend) + logarithmic * blend
        splits.append(float(split))
    splits[-1] = far_value
    return tuple(splits)


def _snap_scalar(value: float, quantum: float) -> float:
    if quantum <= 0.0:
        return float(value)
    return round(float(value) / quantum) * quantum


def build_cascaded_shadow_plan(
    camera: Camera3D,
    *,
    aspect: float,
    settings: Renderer2Settings | None = None,
) -> CascadedShadowPlan3D:
    """Build stable camera-relative CSM ranges without allocating GPU resources."""

    config = settings or Renderer2Settings()
    near = max(1e-4, float(camera.near))
    far = min(float(camera.far), float(config.shadow_distance))
    if far <= near:
        far = min(float(camera.far), near + max(1.0, float(config.shadow_distance)))
    if far <= near:
        raise ValueError("camera far plane must be greater than the effective shadow near plane")

    split_depths = practical_cascade_splits(
        near,
        far,
        int(config.shadow_cascades),
        float(config.shadow_split_lambda),
    )
    forward = camera.forward
    previous = near
    cascades: list[ShadowCascade3D] = []
    tangent = math.tan(math.radians(float(camera.fov)) * 0.5)
    safe_aspect = max(1e-6, float(aspect))

    for index, split in enumerate(split_depths):
        span = split - previous
        overlap = span * float(config.shadow_overlap)
        cascade_near = near if index == 0 else max(near, previous - overlap)
        midpoint = (cascade_near + split) * 0.5
        half_height = tangent * split
        half_width = half_height * safe_aspect
        half_depth = (split - cascade_near) * 0.5
        extent = max(half_height, half_width, half_depth, 0.001) * 1.08
        texel_world = (extent * 2.0) / int(config.shadow_resolution)
        raw_focus = camera.position + forward * midpoint
        stable_focus = Vec3(
            _snap_scalar(raw_focus.x, texel_world),
            _snap_scalar(raw_focus.y, texel_world),
            _snap_scalar(raw_focus.z, texel_world),
        )
        cascades.append(
            ShadowCascade3D(
                index=index,
                near=cascade_near,
                far=split,
                blend_start=max(cascade_near, split - overlap),
                focus=stable_focus,
                extent=extent,
                texel_world_size=texel_world,
            )
        )
        previous = split

    return CascadedShadowPlan3D(near=near, far=far, cascades=tuple(cascades))


def _visible(item: object) -> bool:
    return bool(getattr(item, "enabled", True) and getattr(item, "visible", True))


def _distance_squared(a: Vec3, b: Vec3) -> float:
    dx = float(a.x) - float(b.x)
    dy = float(a.y) - float(b.y)
    dz = float(a.z) - float(b.z)
    return dx * dx + dy * dy + dz * dz


class Renderer2Planner:
    """Deterministic pass scheduler and budget estimator for Renderer 2.0.

    This planner is deliberately backend-independent. The OpenGL executor can consume the exact
    same plan while tests and editor tooling can inspect rendering cost without constructing a GPU
    context.
    """

    def __init__(self, settings: Renderer2Settings | None = None) -> None:
        self.settings = settings or Renderer2Settings()

    def _decals(self, objects: tuple[object, ...], camera: Camera3D) -> tuple[Decal3D, ...]:
        if not self.settings.decals or self.settings.max_decals <= 0:
            return ()
        candidates = [item for item in objects if isinstance(item, Decal3D) and _visible(item)]
        candidates.sort(
            key=lambda item: (
                int(item.layer),
                _distance_squared(item.position, camera.position),
                id(item),
            )
        )
        return tuple(candidates[: int(self.settings.max_decals)])

    def plan(
        self,
        scene: object,
        camera: Camera3D,
        *,
        width: int,
        height: int,
    ) -> Renderer2FramePlan:
        if int(width) <= 0 or int(height) <= 0:
            raise ValueError("renderer dimensions must be greater than zero")
        objects = tuple(getattr(scene, "objects", ()))
        visible_opaque = tuple(
            item for item in objects if _visible(item) and isinstance(item, (Cube3D, Mesh3D))
        )
        opaque_count = len(visible_opaque)
        selection = select_lights(objects)
        directional: DirectionalLight3D | None = (
            selection.directional[0] if selection.directional else None
        )

        cascades: CascadedShadowPlan3D | None = None
        if self.settings.cascaded_shadows and directional is not None and opaque_count:
            cascades = build_cascaded_shadow_plan(
                camera,
                aspect=float(width) / float(height),
                settings=self.settings,
            )

        decals = self._decals(objects, camera)
        decal_candidates = sum(1 for item in objects if isinstance(item, Decal3D) and _visible(item))
        passes: list[Renderer2FramePass] = []
        draw_calls = 0

        depth_draws = opaque_count if self.settings.depth_prepass and opaque_count else 0
        if depth_draws:
            passes.append(Renderer2FramePass("depth_prepass", opaque_count, depth_draws))
            draw_calls += depth_draws

        shadow_draws = 0
        if cascades is not None:
            shadow_draws = opaque_count * len(cascades.cascades)
            passes.append(
                Renderer2FramePass("shadow_cascades", shadow_draws, shadow_draws)
            )
            draw_calls += shadow_draws

        if opaque_count:
            passes.append(Renderer2FramePass("opaque", opaque_count, opaque_count))
            draw_calls += opaque_count

        if decals:
            passes.append(Renderer2FramePass("decals", len(decals), len(decals)))
            draw_calls += len(decals)

        ssao_passes = 0
        if self.settings.ssao and opaque_count:
            ssao_passes = 2  # evaluate + edge-aware blur
            passes.append(Renderer2FramePass("ssao", 1, ssao_passes))
            draw_calls += ssao_passes

        bloom_passes = 0
        if self.settings.bloom:
            levels = int(self.settings.bloom_levels)
            passes.append(Renderer2FramePass("bloom_extract", 1, 1))
            passes.append(Renderer2FramePass("bloom_downsample", levels, levels))
            upsample = max(0, levels - 1)
            if upsample:
                passes.append(Renderer2FramePass("bloom_upsample", upsample, upsample))
            bloom_passes = 1 + levels + upsample
            draw_calls += bloom_passes

        hdr_resolves = 1 if self.settings.hdr else 0
        if hdr_resolves:
            passes.append(Renderer2FramePass("hdr_resolve", 1, 1))
            draw_calls += 1

        diagnostics = Renderer2Diagnostics(
            frame_passes=len(passes),
            visible_opaque=opaque_count,
            depth_prepass_draws=depth_draws,
            shadow_cascades=0 if cascades is None else len(cascades.cascades),
            shadow_draws=shadow_draws,
            decal_candidates=decal_candidates,
            decals_submitted=len(decals),
            decals_dropped=max(0, decal_candidates - len(decals)),
            ssao_passes=ssao_passes,
            bloom_passes=bloom_passes,
            hdr_resolves=hdr_resolves,
            estimated_draw_calls=draw_calls,
        )
        return Renderer2FramePlan(
            passes=tuple(passes),
            cascades=cascades,
            decals=decals,
            diagnostics=diagnostics,
        )
