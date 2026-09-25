from __future__ import annotations

import math
from dataclasses import dataclass

from .gpu_particles import GPUParticleEmitter3D
from .particles import ParticleEmitter2D
from .vfx_authoring22 import EditorVFXTooling22
from .vfx_schema22 import MAX_VFX_CAPACITY22, EditorVFXError22, VFXEffectSpec22

MAX_VFX_PREVIEW_STEP = 0.1
MAX_VFX_PREVIEW_BURST = 4_096


@dataclass(frozen=True, slots=True)
class VFXPreset22:
    name: str
    label: str
    settings: tuple[tuple[str, object], ...]


VFX_PRESETS_22 = (
    VFXPreset22(
        "soft-smoke-2d",
        "Soft Smoke 2D",
        (
            ("backend", "cpu2d"), ("capacity", 192), ("rate", 24.0),
            ("lifetime", (1.1, 2.2)), ("speed", (18.0, 45.0)),
            ("angle", (70.0, 110.0)), ("size", (6.0, 14.0)),
            ("gravity", (0.0, 8.0, 0.0)),
            ("start_color", (0.55, 0.58, 0.62, 0.55)),
            ("end_color", (0.35, 0.38, 0.42, 0.0)),
            ("end_size_scale", 2.4), ("drag", 0.7),
            ("emission_shape", "circle"), ("emission_extent", (18.0, 8.0, 0.0)),
            ("seed", 11),
        ),
    ),
    VFXPreset22(
        "sparks-2d",
        "Sparks 2D",
        (
            ("backend", "cpu2d"), ("capacity", 256), ("rate", 90.0),
            ("lifetime", (0.25, 0.8)), ("speed", (120.0, 260.0)),
            ("angle", (20.0, 160.0)), ("size", (1.5, 4.0)),
            ("gravity", (0.0, -260.0, 0.0)),
            ("start_color", (1.0, 0.8, 0.25, 1.0)),
            ("end_color", (1.0, 0.15, 0.02, 0.0)),
            ("end_size_scale", 0.2), ("drag", 0.2), ("seed", 21),
        ),
    ),
    VFXPreset22(
        "fire-gpu",
        "Fire GPU",
        (
            ("backend", "gpu3d"), ("capacity", 8192), ("rate", 950.0),
            ("lifetime", (0.45, 1.35)), ("size", (5.0, 18.0)),
            ("gravity", (0.0, 1.8, 0.0)), ("velocity_min", (-0.8, 1.5, -0.8)),
            ("velocity_max", (0.8, 4.5, 0.8)), ("drag", 0.35),
            ("start_color", (1.0, 0.55, 0.12, 1.0)),
            ("end_color", (0.9, 0.05, 0.01, 0.0)),
            ("end_size_scale", 0.45), ("emissive_strength", 1.4),
            ("emission_shape", "sphere"), ("emission_extent", (0.5, 0.2, 0.5)),
            ("seed", 31),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class VFXPreviewDiagnostics22:
    backend: str
    capacity: int
    active_or_queued: int
    emitted_total: int
    recycled_total: int
    submitted_total: int
    work_visits_or_frames: int
    last_step: float
    step_was_clamped: bool


@dataclass(frozen=True, slots=True)
class VFXEditorFrame22:
    selected: str | None
    effect_names: tuple[str, ...]
    backend: str | None
    dirty: bool
    preview_running: bool
    diagnostics: VFXPreviewDiagnostics22 | None = None
    messages: tuple[str, ...] = ()


class EditorVFXPanelController22:
    """Toolkit-neutral Particle/VFX Editor controller over shipping runtimes."""

    def __init__(self, tooling: EditorVFXTooling22) -> None:
        self.tooling = tooling
        names = tuple(item.name for item in tooling.effects())
        self._selected = names[0] if names else None
        self._runtime: ParticleEmitter2D | GPUParticleEmitter3D | None = None
        self._preview_running = False
        self._last_step = 0.0
        self._step_was_clamped = False
        self._status = "Particle/VFX Editor ready"

    @property
    def status(self) -> str:
        return self._status

    @property
    def presets(self) -> tuple[VFXPreset22, ...]:
        return VFX_PRESETS_22

    def selected_spec(self) -> VFXEffectSpec22:
        if self._selected is None:
            raise EditorVFXError22("no VFX effect is selected")
        return self.tooling.require(self._selected)

    def frame(self) -> VFXEditorFrame22:
        names = tuple(item.name for item in self.tooling.effects())
        if self._selected not in names:
            self._selected = names[0] if names else None
            self._invalidate_preview()
        backend = None if self._selected is None else self.tooling.require(self._selected).backend
        missing = () if self._selected is None else self.tooling.missing_assets(self._selected)
        return VFXEditorFrame22(
            self._selected,
            names,
            backend,
            self.tooling.dirty,
            self._preview_running,
            self._diagnostics(),
            tuple(f"Missing asset: {path}" for path in missing),
        )

    def select(self, name: str) -> VFXEditorFrame22:
        self.tooling.require(name)
        self._selected = name
        self._invalidate_preview()
        self._status = f"Selected VFX effect {name}"
        return self.frame()

    def create(
        self,
        name: str,
        *,
        preset: str | None = None,
        backend: str = "cpu2d",
    ) -> VFXEditorFrame22:
        settings = {"backend": backend}
        if preset is not None:
            settings = dict(self._preset(preset).settings)
        self.tooling.create_effect(name, **settings)
        self._selected = str(name).strip()
        self._invalidate_preview()
        self._status = f"Created VFX effect {self._selected}"
        return self.frame()

    def apply_preset(self, preset: str) -> VFXEditorFrame22:
        current = self.selected_spec()
        resolved = self._preset(preset)
        self.tooling.replace_effect(
            current.name,
            VFXEffectSpec22(current.name, **dict(resolved.settings)),
        )
        self._invalidate_preview()
        self._status = f"Applied {resolved.label} preset"
        return self.frame()

    def update_common(self, *, capacity: int, rate: float) -> VFXEditorFrame22:
        current = self.selected_spec()
        self.tooling.update_effect(current.name, capacity=capacity, rate=rate)
        self._invalidate_preview()
        self._status = f"Updated emitter settings for {current.name}"
        return self.frame()

    def validate(self) -> tuple[str, ...]:
        current = self.selected_spec()
        preview = self.tooling.preview(current.name)
        messages = tuple(f"Missing asset: {path}" for path in preview.missing_assets)
        if not messages:
            messages = (
                f"{preview.backend} effect validated against the shipping particle runtime.",
            )
        self._status = messages[0]
        return messages

    def start_preview(self) -> VFXEditorFrame22:
        preview = self.tooling.preview(self.selected_spec().name)
        if preview.missing_assets:
            raise EditorVFXError22("preview blocked by missing assets")
        self._runtime = preview.runtime
        self._preview_running = True
        self._last_step = 0.0
        self._step_was_clamped = False
        self._status = f"Preview started for {preview.name}"
        return self.frame()

    def pause_preview(self) -> VFXEditorFrame22:
        self._preview_running = False
        self._status = "Preview paused"
        return self.frame()

    def step_preview(self, dt: float) -> VFXEditorFrame22:
        runtime = self._require_runtime()
        requested = float(dt)
        if not math.isfinite(requested) or requested <= 0:
            raise EditorVFXError22("preview step must be finite and greater than zero")
        step = min(requested, MAX_VFX_PREVIEW_STEP)
        self._last_step = step
        self._step_was_clamped = step != requested
        runtime.update(step)
        self._status = f"Preview stepped {step:.4f}s" + (
            " (clamped)" if self._step_was_clamped else ""
        )
        return self.frame()

    def burst(self, count: int = 16) -> VFXEditorFrame22:
        requested = int(count)
        if requested < 0:
            raise EditorVFXError22("preview burst count must be non-negative")
        bounded = min(requested, MAX_VFX_PREVIEW_BURST, MAX_VFX_CAPACITY22)
        emitted = self._require_runtime().emit(bounded)
        suffix = " (clamped)" if bounded != requested else ""
        self._status = f"Queued/emitted {emitted} particles{suffix}"
        return self.frame()

    def clear_preview(self) -> VFXEditorFrame22:
        self._require_runtime().clear()
        self._last_step = 0.0
        self._step_was_clamped = False
        self._status = "Preview particles cleared"
        return self.frame()

    def save(self) -> VFXEditorFrame22:
        self.tooling.save()
        self._status = "Saved VFX library"
        return self.frame()

    def _require_runtime(self) -> ParticleEmitter2D | GPUParticleEmitter3D:
        if self._runtime is None:
            raise EditorVFXError22("VFX preview is not active")
        return self._runtime

    def _diagnostics(self) -> VFXPreviewDiagnostics22 | None:
        runtime = self._runtime
        if runtime is None:
            return None
        d = runtime.diagnostics
        if isinstance(runtime, ParticleEmitter2D):
            return VFXPreviewDiagnostics22(
                "cpu2d",
                d.capacity,
                d.alive,
                d.emitted_total,
                d.recycled_total,
                d.emitted_total,
                d.update_visits,
                self._last_step,
                self._step_was_clamped,
            )
        return VFXPreviewDiagnostics22(
            "gpu3d",
            d.capacity,
            d.queued,
            d.emitted_total,
            d.recycled_total,
            d.submitted_total,
            d.simulation_frames,
            self._last_step,
            self._step_was_clamped,
        )

    def _invalidate_preview(self) -> None:
        self._runtime = None
        self._preview_running = False
        self._last_step = 0.0
        self._step_was_clamped = False

    @staticmethod
    def _preset(name: str) -> VFXPreset22:
        key = str(name).strip().lower()
        for preset in VFX_PRESETS_22:
            if preset.name == key:
                return preset
        raise EditorVFXError22("unknown VFX preset")
