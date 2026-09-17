from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic, TypeVar

PipelineT = TypeVar("PipelineT")


def _token(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > 128:
        raise ValueError(f"{label} must contain at most 128 characters")
    return result


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _integer(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    return value


def _bool(value: bool, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a boolean")
    return value


def _pairs(values: Iterable[tuple[str, str]], *, label: str) -> tuple[tuple[str, str], ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be an iterable of key/value pairs")
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError(f"{label} entries must be (name, value) tuples")
        key = _token(item[0], label=f"{label} key")
        value = _token(item[1], label=f"{label} value")
        if key in seen:
            raise ValueError(f"duplicate {label} key: {key}")
        seen.add(key)
        normalized.append((key, value))
    return tuple(sorted(normalized))


class RenderSubmissionError(RuntimeError):
    """Stable creator-facing material submission / pipeline-cache failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PipelineStateKey:
    """Backend-neutral immutable key for one render pipeline/program state."""

    shader: str
    vertex_layout: str = "default"
    blend_mode: str = "opaque"
    depth_mode: str = "less-write"
    cull_mode: str = "back"
    topology: str = "triangles"
    render_target: str = "default"
    samples: int = 1
    variants: tuple[tuple[str, str], ...] = ()
    _fingerprint: str = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "shader", _token(self.shader, label="shader"))
        object.__setattr__(self, "vertex_layout", _token(self.vertex_layout, label="vertex_layout"))
        object.__setattr__(self, "blend_mode", _token(self.blend_mode, label="blend_mode"))
        object.__setattr__(self, "depth_mode", _token(self.depth_mode, label="depth_mode"))
        object.__setattr__(self, "cull_mode", _token(self.cull_mode, label="cull_mode"))
        object.__setattr__(self, "topology", _token(self.topology, label="topology"))
        object.__setattr__(self, "render_target", _token(self.render_target, label="render_target"))
        object.__setattr__(self, "samples", _positive_int(self.samples, label="samples"))
        object.__setattr__(self, "variants", _pairs(self.variants, label="variants"))
        payload = {
            "shader": self.shader,
            "vertex_layout": self.vertex_layout,
            "blend_mode": self.blend_mode,
            "depth_mode": self.depth_mode,
            "cull_mode": self.cull_mode,
            "topology": self.topology,
            "render_target": self.render_target,
            "samples": self.samples,
            "variants": [list(item) for item in self.variants],
        }
        object.__setattr__(
            self,
            "_fingerprint",
            hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        )

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "shader": self.shader,
                "vertex_layout": self.vertex_layout,
                "blend_mode": self.blend_mode,
                "depth_mode": self.depth_mode,
                "cull_mode": self.cull_mode,
                "topology": self.topology,
                "render_target": self.render_target,
                "samples": self.samples,
                "variants": [list(item) for item in self.variants],
            }
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint


@dataclass(frozen=True, slots=True)
class MaterialKey:
    """Stable material identity layered on top of a pipeline state."""

    material_id: str
    textures: tuple[str, ...] = ()
    uniform_layout: str = "default"
    _fingerprint: str = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_id", _token(self.material_id, label="material_id"))
        object.__setattr__(self, "uniform_layout", _token(self.uniform_layout, label="uniform_layout"))
        if isinstance(self.textures, (str, bytes)):
            raise TypeError("textures must be an iterable of texture ids, not a string")
        textures: list[str] = []
        for texture in self.textures:
            textures.append(_token(texture, label="texture id"))
        object.__setattr__(self, "textures", tuple(textures))
        payload = {
            "material_id": self.material_id,
            "textures": list(self.textures),
            "uniform_layout": self.uniform_layout,
        }
        object.__setattr__(
            self,
            "_fingerprint",
            hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        )

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "material_id": self.material_id,
                "textures": list(self.textures),
                "uniform_layout": self.uniform_layout,
            }
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint


@dataclass(frozen=True, slots=True)
class DrawSubmission:
    sequence: int
    draw_id: str
    pipeline: PipelineStateKey
    material: MaterialKey
    mesh_id: str
    layer: int
    sort_depth: int
    preserve_order: bool

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "sequence": self.sequence,
                "draw_id": self.draw_id,
                "pipeline": dict(self.pipeline.portable()),
                "material": dict(self.material.portable()),
                "mesh_id": self.mesh_id,
                "layer": self.layer,
                "sort_depth": self.sort_depth,
                "preserve_order": self.preserve_order,
            }
        )


@dataclass(frozen=True, slots=True)
class SubmissionDiagnostics:
    authored_draws: int
    compiled_draws: int
    reorderable_draws: int
    ordered_draws: int
    sort_segments: int
    authored_pipeline_switches: int
    compiled_pipeline_switches: int
    authored_material_switches: int
    compiled_material_switches: int
    pipeline_switches_saved: int
    material_switches_saved: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {name: getattr(self, name) for name in self.__dataclass_fields__}
        )


@dataclass(frozen=True, slots=True)
class MaterialSubmissionPlan:
    draws: tuple[DrawSubmission, ...]
    diagnostics: SubmissionDiagnostics
    fingerprint: str

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "draws": [dict(draw.portable()) for draw in self.draws],
                "diagnostics": dict(self.diagnostics.portable()),
                "fingerprint": self.fingerprint,
            }
        )


class MaterialSubmissionQueue:
    """Bounded deterministic draw planner with explicit order barriers.

    Reorderable runs are state-sorted to reduce backend pipeline/material changes.
    A ``preserve_order=True`` draw is an ordering barrier: neither that draw nor work
    on either side of it can be moved across the barrier. This gives transparent,
    UI, post-process, or creator-sensitive draws an opt-in strict ordering path.
    """

    def __init__(self, *, max_draws: int = 65_536) -> None:
        self.max_draws = _positive_int(max_draws, label="max_draws")
        self._draws: list[DrawSubmission] = []
        self._sequence = 0

    @property
    def authored_draws(self) -> tuple[DrawSubmission, ...]:
        return tuple(self._draws)

    def submit(
        self,
        draw_id: str,
        pipeline: PipelineStateKey,
        material: MaterialKey,
        mesh_id: str,
        *,
        layer: int = 0,
        sort_depth: int = 0,
        preserve_order: bool = False,
    ) -> DrawSubmission:
        if len(self._draws) >= self.max_draws:
            raise RenderSubmissionError("draw-limit", "material submission draw limit reached")
        draw_id = _token(draw_id, label="draw_id")
        mesh_id = _token(mesh_id, label="mesh_id")
        if not isinstance(pipeline, PipelineStateKey):
            raise TypeError("pipeline must be a PipelineStateKey")
        if not isinstance(material, MaterialKey):
            raise TypeError("material must be a MaterialKey")
        layer = _integer(layer, label="layer")
        sort_depth = _integer(sort_depth, label="sort_depth")
        preserve_order = _bool(preserve_order, label="preserve_order")
        self._sequence += 1
        draw = DrawSubmission(
            sequence=self._sequence,
            draw_id=draw_id,
            pipeline=pipeline,
            material=material,
            mesh_id=mesh_id,
            layer=layer,
            sort_depth=sort_depth,
            preserve_order=preserve_order,
        )
        self._draws.append(draw)
        return draw

    def clear(self) -> None:
        self._draws.clear()
        self._sequence = 0

    def compile(self) -> MaterialSubmissionPlan:
        ordered: list[DrawSubmission] = []
        segment: list[DrawSubmission] = []
        sort_segments = 0
        reorderable = 0
        ordered_count = 0

        def flush_segment() -> None:
            nonlocal sort_segments, reorderable
            if not segment:
                return
            sort_segments += 1
            reorderable += len(segment)
            segment.sort(key=self._state_sort_key)
            ordered.extend(segment)
            segment.clear()

        for draw in self._draws:
            if draw.preserve_order:
                flush_segment()
                ordered.append(draw)
                ordered_count += 1
            else:
                segment.append(draw)
        flush_segment()

        authored_pipeline_switches = self._switches(self._draws, lambda draw: draw.pipeline)
        compiled_pipeline_switches = self._switches(ordered, lambda draw: draw.pipeline)
        authored_material_switches = self._switches(self._draws, lambda draw: draw.material)
        compiled_material_switches = self._switches(ordered, lambda draw: draw.material)
        diagnostics = SubmissionDiagnostics(
            authored_draws=len(self._draws),
            compiled_draws=len(ordered),
            reorderable_draws=reorderable,
            ordered_draws=ordered_count,
            sort_segments=sort_segments,
            authored_pipeline_switches=authored_pipeline_switches,
            compiled_pipeline_switches=compiled_pipeline_switches,
            authored_material_switches=authored_material_switches,
            compiled_material_switches=compiled_material_switches,
            pipeline_switches_saved=max(0, authored_pipeline_switches - compiled_pipeline_switches),
            material_switches_saved=max(0, authored_material_switches - compiled_material_switches),
        )
        payload = {
            "draws": [dict(draw.portable()) for draw in ordered],
            "diagnostics": dict(diagnostics.portable()),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return MaterialSubmissionPlan(tuple(ordered), diagnostics, fingerprint)

    @staticmethod
    def _state_sort_key(draw: DrawSubmission) -> tuple[object, ...]:
        return (
            draw.layer,
            draw.pipeline.fingerprint,
            draw.material.fingerprint,
            draw.sort_depth,
            draw.mesh_id,
            draw.sequence,
        )

    @staticmethod
    def _switches(draws: Iterable[DrawSubmission], key: Callable[[DrawSubmission], object]) -> int:
        switches = 0
        sentinel = object()
        previous: object = sentinel
        for draw in draws:
            current = key(draw)
            if previous is not sentinel and current != previous:
                switches += 1
            previous = current
        return switches


@dataclass(frozen=True, slots=True)
class PipelineCacheDiagnostics:
    resident_entries: int
    peak_entries: int
    hits: int
    misses: int
    creates: int
    evictions: int
    invalidations: int
    create_failures: int
    destroy_failures: int
    closed: bool

    def portable(self) -> Mapping[str, int | bool]:
        return MappingProxyType(
            {name: getattr(self, name) for name in self.__dataclass_fields__}
        )


@dataclass(slots=True)
class _PipelineEntry(Generic[PipelineT]):
    key: PipelineStateKey
    pipeline: PipelineT
    last_touch: int


class PipelineStateCache(Generic[PipelineT]):
    """Bounded deterministic LRU cache owning backend pipeline/program objects."""

    def __init__(
        self,
        *,
        create: Callable[[PipelineStateKey], PipelineT],
        destroy: Callable[[PipelineT], None],
        max_entries: int = 256,
    ) -> None:
        if not callable(create):
            raise TypeError("create must be callable")
        if not callable(destroy):
            raise TypeError("destroy must be callable")
        self._create = create
        self._destroy = destroy
        self.max_entries = _positive_int(max_entries, label="max_entries")
        self._entries: dict[PipelineStateKey, _PipelineEntry[PipelineT]] = {}
        self._touch = 0
        self._peak_entries = 0
        self._hits = 0
        self._misses = 0
        self._creates = 0
        self._evictions = 0
        self._invalidations = 0
        self._create_failures = 0
        self._destroy_failures = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def diagnostics(self) -> PipelineCacheDiagnostics:
        return PipelineCacheDiagnostics(
            resident_entries=len(self._entries),
            peak_entries=self._peak_entries,
            hits=self._hits,
            misses=self._misses,
            creates=self._creates,
            evictions=self._evictions,
            invalidations=self._invalidations,
            create_failures=self._create_failures,
            destroy_failures=self._destroy_failures,
            closed=self._closed,
        )

    def get_or_create(self, key: PipelineStateKey) -> PipelineT:
        self._ensure_open()
        if not isinstance(key, PipelineStateKey):
            raise TypeError("key must be a PipelineStateKey")
        existing = self._entries.get(key)
        if existing is not None:
            self._hits += 1
            self._touch_entry(existing)
            return existing.pipeline

        self._misses += 1
        try:
            pipeline = self._create(key)
        except Exception as exc:
            self._create_failures += 1
            raise RenderSubmissionError("pipeline-create-failed", f"pipeline creation failed: {exc}") from exc

        if len(self._entries) >= self.max_entries:
            victim = min(
                self._entries.values(),
                key=lambda entry: (entry.last_touch, entry.key.fingerprint),
            )
            try:
                self._destroy(victim.pipeline)
            except Exception as exc:
                self._destroy_failures += 1
                self._destroy_untracked_pipeline(pipeline)
                raise RenderSubmissionError(
                    "pipeline-evict-failed", f"pipeline eviction failed: {exc}"
                ) from exc
            del self._entries[victim.key]
            self._evictions += 1

        self._touch += 1
        self._entries[key] = _PipelineEntry(key=key, pipeline=pipeline, last_touch=self._touch)
        self._creates += 1
        self._peak_entries = max(self._peak_entries, len(self._entries))
        return pipeline

    def prepare(self, plan: MaterialSubmissionPlan) -> tuple[tuple[DrawSubmission, PipelineT], ...]:
        self._ensure_open()
        if not isinstance(plan, MaterialSubmissionPlan):
            raise TypeError("plan must be a MaterialSubmissionPlan")
        prepared: list[tuple[DrawSubmission, PipelineT]] = []
        for draw in plan.draws:
            prepared.append((draw, self.get_or_create(draw.pipeline)))
        return tuple(prepared)

    def invalidate(self, key: PipelineStateKey) -> bool:
        self._ensure_open()
        if not isinstance(key, PipelineStateKey):
            raise TypeError("key must be a PipelineStateKey")
        entry = self._entries.get(key)
        if entry is None:
            return False
        try:
            self._destroy(entry.pipeline)
        except Exception as exc:
            self._destroy_failures += 1
            raise RenderSubmissionError(
                "pipeline-invalidate-failed", f"pipeline invalidation failed: {exc}"
            ) from exc
        del self._entries[key]
        self._invalidations += 1
        return True

    def invalidate_shader(self, shader: str) -> int:
        self._ensure_open()
        shader = _token(shader, label="shader")
        invalidated = 0
        failures: list[str] = []
        keys = sorted(
            (key for key in self._entries if key.shader == shader),
            key=lambda key: key.fingerprint,
        )
        for key in keys:
            entry = self._entries.get(key)
            if entry is None:
                continue
            try:
                self._destroy(entry.pipeline)
            except Exception as exc:  # noqa: BLE001 - backend callback failures are isolated per entry
                self._destroy_failures += 1
                failures.append(str(exc))
                continue
            del self._entries[key]
            self._invalidations += 1
            invalidated += 1
        if failures:
            raise RenderSubmissionError(
                "pipeline-invalidate-failed",
                f"{len(failures)} pipeline invalidation(s) failed; {invalidated} succeeded",
            )
        return invalidated

    def clear(self) -> int:
        self._ensure_open()
        destroyed = 0
        failures = 0
        for key in sorted(self._entries, key=lambda item: item.fingerprint):
            entry = self._entries.get(key)
            if entry is None:
                continue
            try:
                self._destroy(entry.pipeline)
            except Exception:  # noqa: BLE001 - continue cleaning independent backend entries
                self._destroy_failures += 1
                failures += 1
                continue
            del self._entries[key]
            self._invalidations += 1
            destroyed += 1
        if failures:
            raise RenderSubmissionError(
                "pipeline-clear-failed",
                f"{failures} pipeline(s) could not be destroyed; {destroyed} cleared",
            )
        return destroyed

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.clear()
        except RenderSubmissionError as exc:
            raise RenderSubmissionError("pipeline-close-failed", str(exc)) from exc
        self._closed = True

    def state_fingerprint(self) -> str:
        state = {
            "entries": [
                {
                    "key": dict(entry.key.portable()),
                    "last_touch": entry.last_touch,
                }
                for entry in sorted(
                    self._entries.values(), key=lambda item: item.key.fingerprint
                )
            ],
            "diagnostics": dict(self.diagnostics().portable()),
        }
        return hashlib.sha256(
            json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _touch_entry(self, entry: _PipelineEntry[PipelineT]) -> None:
        self._touch += 1
        entry.last_touch = self._touch

    def _destroy_untracked_pipeline(self, pipeline: PipelineT) -> None:
        try:
            self._destroy(pipeline)
        except Exception as exc:
            self._destroy_failures += 1
            raise RenderSubmissionError(
                "pipeline-rollback-failed",
                f"pipeline eviction failed and rollback destruction also failed: {exc}",
            ) from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise RenderSubmissionError("cache-closed", "pipeline state cache is closed")
