from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .graphics.material import Material3D
from .graphics.shader_mesh import shader_material_3d
from .graphics.shader_pipeline import ShaderMaterial3D, ShaderPipelineError, ShaderSafetyError
from .math.types import Color

MATERIAL_LIBRARY_FORMAT = "swirengine.material-library"
MATERIAL_LIBRARY_VERSION = 1
DEFAULT_MATERIAL_LIBRARY_PATH = "config/materials.json"


class EditorMaterialToolingError(ValueError):
    """Raised when project material/shader data cannot be authored safely."""


DefineValue22 = bool | int | float | str
UniformValue22 = bool | int | float | tuple[float, ...]


@dataclass(frozen=True, slots=True)
class MaterialAssetSpec22:
    name: str
    texture: str | None = None
    tint: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    ambient: float = 0.25
    diffuse: float = 0.75
    specular: float = 0.35
    shininess: float = 32.0
    metallic: float | None = None
    roughness: float | None = None
    metallic_roughness_texture: str | None = None
    normal_texture: str | None = None
    normal_scale: float = 1.0
    occlusion_texture: str | None = None
    occlusion_strength: float = 1.0
    emissive_texture: str | None = None
    emissive_factor: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    alpha_mode: str = "OPAQUE"
    alpha_cutoff: float = 0.5
    double_sided: bool = False
    shader_defines: tuple[tuple[str, DefineValue22], ...] = ()
    shader_hooks: tuple[tuple[str, str], ...] = ()
    shader_uniforms: tuple[tuple[str, UniformValue22], ...] = ()
    strict_uniforms: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name))
        for field_name in (
            "texture",
            "metallic_roughness_texture",
            "normal_texture",
            "occlusion_texture",
            "emissive_texture",
        ):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None if value is None else _asset_path(value, field_name.replace("_", " ")),
            )

        object.__setattr__(self, "tint", _color(self.tint, "material tint"))
        object.__setattr__(self, "ambient", _non_negative(self.ambient, "material ambient"))
        object.__setattr__(self, "diffuse", _non_negative(self.diffuse, "material diffuse"))
        object.__setattr__(self, "specular", _non_negative(self.specular, "material specular"))
        object.__setattr__(self, "shininess", _positive(self.shininess, "material shininess"))
        object.__setattr__(
            self,
            "metallic",
            None if self.metallic is None else _unit(self.metallic, "material metallic"),
        )
        object.__setattr__(
            self,
            "roughness",
            None if self.roughness is None else _unit(self.roughness, "material roughness"),
        )
        object.__setattr__(
            self,
            "normal_scale",
            _non_negative(self.normal_scale, "material normal scale"),
        )
        object.__setattr__(
            self,
            "occlusion_strength",
            _unit(self.occlusion_strength, "material occlusion strength"),
        )
        object.__setattr__(
            self,
            "emissive_factor",
            _non_negative_color(self.emissive_factor, "material emissive factor"),
        )

        alpha_mode = str(self.alpha_mode).strip().upper()
        if alpha_mode not in {"OPAQUE", "MASK", "BLEND"}:
            raise EditorMaterialToolingError("material alpha mode must be OPAQUE, MASK or BLEND")
        object.__setattr__(self, "alpha_mode", alpha_mode)
        object.__setattr__(
            self,
            "alpha_cutoff",
            _unit(self.alpha_cutoff, "material alpha cutoff"),
        )
        object.__setattr__(self, "double_sided", bool(self.double_sided))
        object.__setattr__(self, "strict_uniforms", bool(self.strict_uniforms))

        defines = _define_pairs(self.shader_defines)
        hooks = _hook_pairs(self.shader_hooks)
        uniforms = _uniform_pairs(self.shader_uniforms)
        object.__setattr__(self, "shader_defines", defines)
        object.__setattr__(self, "shader_hooks", hooks)
        object.__setattr__(self, "shader_uniforms", uniforms)

        if defines or hooks or uniforms:
            try:
                shader_material_3d(
                    defines=dict(defines),
                    hooks=dict(hooks),
                    uniforms=dict(uniforms),
                    strict_uniforms=self.strict_uniforms,
                )
            except (ShaderPipelineError, ShaderSafetyError, TypeError, ValueError) as exc:
                raise EditorMaterialToolingError(
                    f"invalid material shader configuration: {exc}"
                ) from exc


@dataclass(frozen=True, slots=True)
class MaterialPreview22:
    name: str
    material: Material3D
    shader_material: ShaderMaterial3D | None
    missing_assets: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class EditorMaterialSnapshot22:
    path: str
    materials: tuple[MaterialAssetSpec22, ...]
    dirty: bool

    @property
    def material_count(self) -> int:
        return len(self.materials)


class EditorMaterialTooling22:
    """Deterministic material/shader authoring backed by shipping runtime types."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        path: str = DEFAULT_MATERIAL_LIBRARY_PATH,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.assets_root = (self.project_root / "assets").resolve()
        self.relative_path = _relative_path(path)
        self._materials: dict[str, MaterialAssetSpec22] = {}
        self._saved_fingerprint = self._fingerprint()
        if self.target.is_file():
            self.load()

    @property
    def target(self) -> Path:
        return _target(self.project_root, self.relative_path)

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorMaterialSnapshot22:
        return EditorMaterialSnapshot22(
            path=self.relative_path,
            materials=self._ordered_materials(),
            dirty=self.dirty,
        )

    def create_material(self, name: str, **settings: Any) -> EditorMaterialSnapshot22:
        spec = MaterialAssetSpec22(name=name, **settings)
        if spec.name in self._materials:
            raise EditorMaterialToolingError(f"material {spec.name!r} already exists")
        self._materials[spec.name] = spec
        return self.snapshot()

    def update_material(self, name: str, **changes: Any) -> EditorMaterialSnapshot22:
        if "name" in changes:
            raise EditorMaterialToolingError("material name changes require duplicate/remove")
        current = self._require(name)
        updated = replace(current, **changes)
        self._materials[name] = updated
        return self.snapshot()

    def duplicate_material(self, name: str, new_name: str) -> EditorMaterialSnapshot22:
        current = self._require(name)
        duplicate = replace(current, name=_name(new_name))
        if duplicate.name in self._materials:
            raise EditorMaterialToolingError(f"material {duplicate.name!r} already exists")
        self._materials[duplicate.name] = duplicate
        return self.snapshot()

    def remove_material(self, name: str) -> EditorMaterialSnapshot22:
        self._require(name)
        del self._materials[name]
        return self.snapshot()

    def build_material(self, name: str) -> Material3D:
        spec = self._require(name)
        return Material3D(
            texture=self._runtime_asset(spec.texture),
            tint=Color(*spec.tint),
            ambient=spec.ambient,
            diffuse=spec.diffuse,
            specular=spec.specular,
            shininess=spec.shininess,
            metallic=spec.metallic,
            roughness=spec.roughness,
            metallic_roughness_texture=self._runtime_asset(spec.metallic_roughness_texture),
            normal_texture=self._runtime_asset(spec.normal_texture),
            normal_scale=spec.normal_scale,
            occlusion_texture=self._runtime_asset(spec.occlusion_texture),
            occlusion_strength=spec.occlusion_strength,
            emissive_texture=self._runtime_asset(spec.emissive_texture),
            emissive_factor=Color(*spec.emissive_factor),
            alpha_mode=spec.alpha_mode,
            alpha_cutoff=spec.alpha_cutoff,
            double_sided=spec.double_sided,
        )

    def build_shader_material(self, name: str) -> ShaderMaterial3D | None:
        spec = self._require(name)
        if not (spec.shader_defines or spec.shader_hooks or spec.shader_uniforms):
            return None
        try:
            return shader_material_3d(
                defines=dict(spec.shader_defines),
                hooks=dict(spec.shader_hooks),
                uniforms=dict(spec.shader_uniforms),
                strict_uniforms=spec.strict_uniforms,
            )
        except (ShaderPipelineError, ShaderSafetyError, TypeError, ValueError) as exc:
            raise EditorMaterialToolingError(f"cannot prepare material shader: {exc}") from exc

    def missing_assets(self, name: str) -> tuple[str, ...]:
        spec = self._require(name)
        missing: list[str] = []
        for value in _asset_values(spec):
            if not (self.assets_root / PurePosixPath(value)).is_file():
                missing.append(value)
        return tuple(sorted(set(missing)))

    def preview(self, name: str) -> MaterialPreview22:
        spec = self._require(name)
        return MaterialPreview22(
            name=spec.name,
            material=self.build_material(name),
            shader_material=self.build_shader_material(name),
            missing_assets=self.missing_assets(name),
            fingerprint=_spec_fingerprint(spec),
        )

    def save(self) -> EditorMaterialSnapshot22:
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
                handle.write(self._serialized_text())
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, target)
            temporary = None
        except OSError as exc:
            raise EditorMaterialToolingError(f"cannot save material library: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def load(self) -> EditorMaterialSnapshot22:
        try:
            payload = json.loads(self.target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorMaterialToolingError(f"cannot load material library: {exc}") from exc
        materials = _decode(payload)
        self._materials = {item.name: item for item in materials}
        if len(self._materials) != len(materials):
            raise EditorMaterialToolingError("duplicate material name")
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def _require(self, name: str) -> MaterialAssetSpec22:
        try:
            return self._materials[str(name)]
        except KeyError as exc:
            raise EditorMaterialToolingError(f"unknown material {name!r}") from exc

    def _ordered_materials(self) -> tuple[MaterialAssetSpec22, ...]:
        return tuple(self._materials[name] for name in sorted(self._materials))

    def _payload(self) -> dict[str, Any]:
        return {
            "format": MATERIAL_LIBRARY_FORMAT,
            "version": MATERIAL_LIBRARY_VERSION,
            "materials": [asdict(item) for item in self._ordered_materials()],
        }

    def _serialized_text(self) -> str:
        return json.dumps(
            self._payload(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"

    def _fingerprint(self) -> str:
        encoded = json.dumps(
            self._payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _runtime_asset(self, value: str | None) -> Path | None:
        if value is None:
            return None
        return (self.assets_root / PurePosixPath(value)).resolve()


def _decode(payload: Any) -> tuple[MaterialAssetSpec22, ...]:
    if not isinstance(payload, dict):
        raise EditorMaterialToolingError("material library must be an object")
    if set(payload) != {"format", "version", "materials"}:
        raise EditorMaterialToolingError("material library fields do not match schema")
    if (
        payload["format"] != MATERIAL_LIBRARY_FORMAT
        or payload["version"] != MATERIAL_LIBRARY_VERSION
    ):
        raise EditorMaterialToolingError("unsupported material library")
    items = payload["materials"]
    if not isinstance(items, list):
        raise EditorMaterialToolingError("material library materials must be an array")
    fields = set(MaterialAssetSpec22.__dataclass_fields__)
    result: list[MaterialAssetSpec22] = []
    for item in items:
        if not isinstance(item, dict) or set(item) - fields:
            raise EditorMaterialToolingError("invalid material library entry")
        try:
            result.append(MaterialAssetSpec22(**item))
        except (TypeError, ValueError) as exc:
            raise EditorMaterialToolingError(f"invalid material library entry: {exc}") from exc
    return tuple(result)


def _name(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("material name must be a string")
    clean = value.strip()
    if not clean:
        raise EditorMaterialToolingError("material name cannot be empty")
    if len(clean) > 96 or "/" in clean or "\\" in clean or "\x00" in clean:
        raise EditorMaterialToolingError("material name must be a portable 1-96 character label")
    return clean


def _relative_path(value: Any) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        not normalized
        or normalized == "."
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorMaterialToolingError("material library path must stay project-relative")
    return posix.as_posix()


def _target(root: Path, relative_path: str) -> Path:
    target = (root / PurePosixPath(relative_path)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise EditorMaterialToolingError("material library path escapes the project") from exc
    return target


def _asset_path(value: Any, label: str) -> str:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{label} must be a path string")
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        not normalized
        or normalized == "."
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorMaterialToolingError(
            f"{label} must stay inside the project assets directory"
        )
    return posix.as_posix()


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EditorMaterialToolingError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise EditorMaterialToolingError(f"{label} must be finite")
    return result


def _non_negative(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0:
        raise EditorMaterialToolingError(f"{label} must be >= 0")
    return result


def _positive(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result <= 0.0:
        raise EditorMaterialToolingError(f"{label} must be > 0")
    return result


def _unit(value: Any, label: str) -> float:
    result = _finite(value, label)
    if not 0.0 <= result <= 1.0:
        raise EditorMaterialToolingError(f"{label} must be within 0..1")
    return result


def _color(value: Any, label: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(value)
    except TypeError as exc:
        raise EditorMaterialToolingError(f"{label} must contain four numeric values") from exc
    if len(values) != 4:
        raise EditorMaterialToolingError(f"{label} must contain four numeric values")
    return tuple(_unit(component, label) for component in values)  # type: ignore[return-value]


def _non_negative_color(value: Any, label: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(value)
    except TypeError as exc:
        raise EditorMaterialToolingError(f"{label} must contain four numeric values") from exc
    if len(values) != 4:
        raise EditorMaterialToolingError(f"{label} must contain four numeric values")
    return tuple(
        _non_negative(component, label) for component in values
    )  # type: ignore[return-value]


def _pair_items(value: Any, label: str) -> tuple[tuple[Any, Any], ...]:
    if isinstance(value, dict):
        items = tuple(value.items())
    else:
        try:
            items = tuple(tuple(item) for item in value)
        except (TypeError, ValueError) as exc:
            raise EditorMaterialToolingError(f"{label} must contain name/value pairs") from exc
    if any(len(item) != 2 for item in items):
        raise EditorMaterialToolingError(f"{label} must contain name/value pairs")
    names = [str(item[0]) for item in items]
    if len(names) != len(set(names)):
        raise EditorMaterialToolingError(f"{label} contains duplicate names")
    return tuple(sorted(items, key=lambda item: str(item[0])))


def _define_pairs(value: Any) -> tuple[tuple[str, DefineValue22], ...]:
    result: list[tuple[str, DefineValue22]] = []
    for name, raw in _pair_items(value, "shader defines"):
        key = str(name)
        if isinstance(raw, (bool, int, float, str)):
            result.append((key, raw))
        else:
            raise EditorMaterialToolingError(
                "shader define values must be bool/int/float/string"
            )
    return tuple(result)


def _hook_pairs(value: Any) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for name, raw in _pair_items(value, "shader hooks"):
        if not isinstance(raw, str):
            raise EditorMaterialToolingError("shader hook source must be a string")
        result.append((str(name), raw))
    return tuple(result)


def _uniform_pairs(value: Any) -> tuple[tuple[str, UniformValue22], ...]:
    result: list[tuple[str, UniformValue22]] = []
    for name, raw in _pair_items(value, "shader uniforms"):
        normalized: UniformValue22
        if isinstance(raw, (bool, int, float)):
            normalized = raw
        elif isinstance(raw, (list, tuple)):
            normalized = tuple(_finite(item, f"shader uniform {name}") for item in raw)
        else:
            raise EditorMaterialToolingError(
                "shader uniform values must be bool/int/float or numeric vectors"
            )
        result.append((str(name), normalized))
    return tuple(result)


def _asset_values(spec: MaterialAssetSpec22) -> tuple[str, ...]:
    return tuple(
        value
        for value in (
            spec.texture,
            spec.metallic_roughness_texture,
            spec.normal_texture,
            spec.occlusion_texture,
            spec.emissive_texture,
        )
        if value is not None
    )


def _spec_fingerprint(spec: MaterialAssetSpec22) -> str:
    payload = json.dumps(
        asdict(spec),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
