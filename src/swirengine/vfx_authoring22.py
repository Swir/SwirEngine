from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from .gpu_particles import GPUParticleEmitter3D
from .math.types import Color, Vec3
from .particles import ParticleEmitter2D
from .vfx_schema22 import EditorVFXError22, VFXEffectSpec22, project_relative_path, safe_target

VFX_LIBRARY_FORMAT = "swirengine.vfx-library"
VFX_LIBRARY_VERSION = 1
DEFAULT_VFX_LIBRARY_PATH = "config/vfx.json"


@dataclass(frozen=True, slots=True)
class VFXRuntimePreview22:
    name: str
    backend: str
    runtime: ParticleEmitter2D | GPUParticleEmitter3D
    missing_assets: tuple[str, ...]
    fingerprint: str


class EditorVFXTooling22:
    """Deterministic creator VFX library backed by shipping particle runtimes."""

    def __init__(self, project_root: str | Path, *, path: str = DEFAULT_VFX_LIBRARY_PATH) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.assets_root = (self.project_root / "assets").resolve()
        try:
            self.assets_root.relative_to(self.project_root)
        except ValueError as exc:
            raise EditorVFXError22(
                "project assets directory must resolve inside the project root"
            ) from exc
        self.relative_path = project_relative_path(path, "VFX library path")
        self._effects: dict[str, VFXEffectSpec22] = {}
        self._saved = self._fingerprint()
        if self.target.is_file():
            self.load()

    @property
    def target(self) -> Path:
        return safe_target(self.project_root, self.relative_path, "VFX library path")

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved

    def effects(self) -> tuple[VFXEffectSpec22, ...]:
        return tuple(self._effects[name] for name in sorted(self._effects))

    def require(self, name: str) -> VFXEffectSpec22:
        try:
            return self._effects[str(name)]
        except KeyError as exc:
            raise EditorVFXError22(f"unknown VFX effect {name!r}") from exc

    def create_effect(self, name: str, **settings: Any) -> VFXEffectSpec22:
        spec = VFXEffectSpec22(name, **settings)
        if spec.name in self._effects:
            raise EditorVFXError22(f"VFX effect {spec.name!r} already exists")
        self._effects[spec.name] = spec
        return spec

    def update_effect(self, name: str, **changes: Any) -> VFXEffectSpec22:
        if "name" in changes:
            raise EditorVFXError22("effect name changes require duplicate/remove")
        current = self.require(name)
        updated = replace(current, **changes)
        self._effects[current.name] = updated
        return updated

    def replace_effect(self, name: str, spec: VFXEffectSpec22) -> VFXEffectSpec22:
        current = self.require(name)
        updated = spec if spec.name == current.name else replace(spec, name=current.name)
        self._effects[current.name] = updated
        return updated

    def missing_assets(self, name: str) -> tuple[str, ...]:
        spec = self.require(name)
        if spec.backend != "gpu3d" or spec.texture is None:
            return ()
        return () if self._asset_target(spec.texture).is_file() else (spec.texture,)

    def build_runtime(self, name: str) -> ParticleEmitter2D | GPUParticleEmitter3D:
        spec = self.require(name)
        if spec.backend == "cpu2d":
            return ParticleEmitter2D(
                max_particles=spec.capacity,
                rate=spec.rate,
                lifetime=spec.lifetime,
                speed=spec.speed,
                angle=spec.angle,
                size=spec.size,
                gravity=spec.gravity[:2],
                color=Color(*spec.start_color),
                seed=spec.seed,
                emission_shape=spec.emission_shape,
                emission_size=spec.emission_extent[:2],
                end_color=Color(*spec.end_color),
                end_size_scale=spec.end_size_scale,
                drag=spec.drag,
            )
        texture = None if spec.texture is None else str(self._asset_target(spec.texture))
        return GPUParticleEmitter3D(
            capacity=spec.capacity,
            rate=spec.rate,
            lifetime=spec.lifetime,
            velocity_min=Vec3(*spec.velocity_min),
            velocity_max=Vec3(*spec.velocity_max),
            gravity=Vec3(*spec.gravity),
            drag=spec.drag,
            size_pixels=spec.size,
            end_size_scale=spec.end_size_scale,
            start_color=Color(*spec.start_color),
            end_color=Color(*spec.end_color),
            emissive_strength=spec.emissive_strength,
            emission_shape=spec.emission_shape,
            emission_extent=Vec3(*spec.emission_extent),
            blend_mode=spec.blend_mode,
            render_mode=spec.render_mode,
            texture=texture,
            trail_enabled=spec.trail_enabled,
            trail_alpha_scale=spec.trail_alpha_scale,
            seed=spec.seed,
        )

    def preview(self, name: str) -> VFXRuntimePreview22:
        spec = self.require(name)
        return VFXRuntimePreview22(
            spec.name,
            spec.backend,
            self.build_runtime(name),
            self.missing_assets(name),
            _fingerprint_spec(spec),
        )

    def save(self) -> None:
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                delete=False,
            ) as handle:
                handle.write(self._serialized())
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved = self._fingerprint()

    def load(self) -> None:
        try:
            payload = json.loads(self.target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorVFXError22(f"cannot load VFX library: {exc}") from exc
        if not isinstance(payload, dict) or set(payload) != {"format", "version", "effects"}:
            raise EditorVFXError22("VFX library fields do not match schema")
        if (
            payload["format"] != VFX_LIBRARY_FORMAT
            or payload["version"] != VFX_LIBRARY_VERSION
            or not isinstance(payload["effects"], list)
        ):
            raise EditorVFXError22("unsupported VFX library")
        try:
            effects = tuple(VFXEffectSpec22(**item) for item in payload["effects"])
        except (TypeError, ValueError) as exc:
            raise EditorVFXError22(f"invalid VFX effect entry: {exc}") from exc
        self._effects = {item.name: item for item in effects}
        if len(self._effects) != len(effects):
            raise EditorVFXError22("duplicate VFX effect name")
        self._saved = self._fingerprint()

    def _payload(self) -> dict[str, Any]:
        return {
            "format": VFX_LIBRARY_FORMAT,
            "version": VFX_LIBRARY_VERSION,
            "effects": [asdict(item) for item in self.effects()],
        }

    def _serialized(self) -> str:
        return json.dumps(self._payload(), indent=2, sort_keys=True, allow_nan=False) + "\n"

    def _fingerprint(self) -> str:
        data = json.dumps(
            self._payload(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        return hashlib.sha256(data).hexdigest()

    def _asset_target(self, value: str) -> Path:
        target = (self.assets_root / PurePosixPath(value)).resolve()
        try:
            target.relative_to(self.assets_root)
        except ValueError as exc:
            raise EditorVFXError22(
                f"VFX asset {value!r} resolves outside the project assets directory"
            ) from exc
        return target


def _fingerprint_spec(spec: VFXEffectSpec22) -> str:
    return hashlib.sha256(
        json.dumps(asdict(spec), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
