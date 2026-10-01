from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .core.game import Game
from .core.scene import SceneMount
from .graphics.environment import Environment3D, Skybox3D
from .graphics.lights import DirectionalLight3D, PointLight3D, SpotLight3D, select_lights
from .graphics.postprocess import PostProcessSettings
from .graphics.renderer2 import Renderer2Settings
from .math.types import Color, Vec3

LIGHTING_FORMAT = "swirengine.scene-lighting"
LIGHTING_VERSION = 1
MAX_LIGHTING_BYTES = 262144
MAX_LIGHTING_SCENES = 128


class EditorLightingError22(ValueError):
    """Invalid, unsafe or unsupported project lighting authoring."""


def _number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditorLightingError22(f"{label} must be a number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise EditorLightingError22(f"{label} is outside numeric range") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise EditorLightingError22(f"{label} must be finite and in [{low}, {high}]")
    return result


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise EditorLightingError22(f"{label} must be a boolean")
    return value


def _vector(value: object, label: str, size: int, low: float, high: float) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != size:
        raise EditorLightingError22(f"{label} must contain {size} numbers")
    return tuple(_number(item, label, low, high) for item in value)


def _path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise EditorLightingError22(f"{label} must be a nonempty relative path")
    path = value.replace("\\", "/")
    if (PureWindowsPath(path).drive or path.startswith("/")
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or any(ord(char) < 32 for char in path) or ":" in path):
        raise EditorLightingError22(f"{label} must stay project-relative")
    return path


def _contained(root: Path, relative: str) -> Path:
    try:
        target = (root / PurePosixPath(relative)).resolve()
        target.relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise EditorLightingError22(f"{relative!r} resolves outside or is invalid in {root}") from exc
    return target


@dataclass(frozen=True, slots=True)
class LightSpec22:
    name: str
    kind: str = "directional"
    position: tuple[float, ...] = (0.0, 3.0, 0.0)
    direction: tuple[float, ...] = (-0.4, -0.8, -0.6)
    color: tuple[float, ...] = (1.0, 1.0, 1.0, 1.0)
    intensity: float = 1.0
    range: float = 10.0
    inner_angle: float = 20.0
    outer_angle: float = 30.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 128:
            raise EditorLightingError22("light name must contain 1-128 characters")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.kind, str) or self.kind not in {"directional", "point", "spot"}:
            raise EditorLightingError22("light kind must be directional, point or spot")
        for key in ("position", "direction"):
            object.__setattr__(self, key, _vector(getattr(self, key), key, 3, -1e6, 1e6))
        if self.kind != "point" and not any(self.direction):
            raise EditorLightingError22("light direction cannot be zero")
        object.__setattr__(self, "color", _vector(self.color, "color", 4, 0.0, 1.0))
        for key, low, high in (("intensity", 0.0, 1000.0), ("range", 0.001, 1e6),
                               ("inner_angle", 0.0, 89.9), ("outer_angle", 0.01, 89.99)):
            object.__setattr__(self, key, _number(getattr(self, key), key, low, high))
        if self.inner_angle >= self.outer_angle:
            raise EditorLightingError22("inner_angle must be less than outer_angle")
        _boolean(self.enabled, "enabled")

    def runtime(self) -> DirectionalLight3D | PointLight3D | SpotLight3D:
        common = dict(name=self.name, color=Color(*self.color), intensity=self.intensity,
                      enabled=self.enabled)
        if self.kind == "directional":
            return DirectionalLight3D(direction=Vec3(*self.direction), **common)
        if self.kind == "point":
            return PointLight3D(position=Vec3(*self.position), range=self.range, **common)
        return SpotLight3D(position=Vec3(*self.position), direction=Vec3(*self.direction),
                           range=self.range, inner_angle=self.inner_angle,
                           outer_angle=self.outer_angle, **common)


@dataclass(frozen=True, slots=True)
class EnvironmentSpec22:
    enabled: bool = False
    sky_color: tuple[float, ...] = (0.48, 0.62, 1.0, 1.0)
    ground_color: tuple[float, ...] = (0.18, 0.16, 0.14, 1.0)
    intensity: float = 0.35
    ground_intensity: float = 0.16
    skybox_texture: str | None = None
    skybox_size: float = 80.0

    def __post_init__(self) -> None:
        _boolean(self.enabled, "environment enabled")
        for key in ("sky_color", "ground_color"):
            object.__setattr__(self, key, _vector(getattr(self, key), key, 4, 0.0, 1.0))
        for key in ("intensity", "ground_intensity"):
            object.__setattr__(self, key, _number(getattr(self, key), key, 0.0, 1000.0))
        object.__setattr__(self, "skybox_size", _number(self.skybox_size, "skybox_size", 0.01, 1e6))
        if self.skybox_texture is not None:
            object.__setattr__(self, "skybox_texture", _path(self.skybox_texture, "skybox texture"))


@dataclass(frozen=True, slots=True)
class PostFXSpec22:
    enabled: bool = True
    tone_mapping: str = "aces"
    exposure: float = 1.0
    gamma: float = 2.2
    contrast: float = 1.0
    saturation: float = 1.0
    vignette: float = 0.0
    fxaa: bool = True

    def __post_init__(self) -> None:
        _boolean(self.enabled, "post-FX enabled")
        _boolean(self.fxaa, "fxaa")
        for key, low, high in (("exposure", 0.001, 64), ("gamma", 0.1, 8),
                               ("contrast", 0, 8), ("saturation", 0, 8), ("vignette", 0, 1)):
            object.__setattr__(self, key, _number(getattr(self, key), key, low, high))
        try:
            PostProcessSettings(**asdict(self))
        except (TypeError, ValueError) as exc:
            raise EditorLightingError22(str(exc)) from exc

    def runtime(self) -> PostProcessSettings:
        return PostProcessSettings(**asdict(self))


def _renderer_settings(settings: Renderer2Settings) -> None:
    if not isinstance(settings, Renderer2Settings):
        raise EditorLightingError22("renderer must be Renderer2Settings")
    defaults = asdict(Renderer2Settings())
    for key, value in asdict(settings).items():
        if isinstance(defaults[key], bool):
            _boolean(value, key)
        elif isinstance(defaults[key], int):
            if isinstance(value, bool) or not isinstance(value, int):
                raise EditorLightingError22(f"{key} must be an integer")
        else:
            _number(value, key, 0.0, 1e6)
    if settings.shadow_resolution > 4096 or settings.max_decals > 4096:
        raise EditorLightingError22("renderer work budget exceeds 4096")
    # Re-run shipping validation even for a value constructed by unusual callers.
    try:
        Renderer2Settings(**asdict(settings))
    except (TypeError, ValueError) as exc:
        raise EditorLightingError22(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SceneLightingSpec22:
    scene: str
    mode: str = "3d"
    lights: tuple[LightSpec22, ...] = ()
    environment: EnvironmentSpec22 = field(default_factory=EnvironmentSpec22)
    postfx: PostFXSpec22 = field(default_factory=PostFXSpec22)
    renderer: Renderer2Settings = field(default_factory=Renderer2Settings)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene", _path(self.scene, "scene"))
        if not isinstance(self.mode, str) or self.mode not in {"2d", "3d"}:
            raise EditorLightingError22("lighting mode must be 2d or 3d")
        if not isinstance(self.lights, (tuple, list)) or len(self.lights) > 12:
            raise EditorLightingError22("lighting profile has too many lights")
        if not all(isinstance(light, LightSpec22) for light in self.lights):
            raise EditorLightingError22("lights must contain LightSpec22 values")
        object.__setattr__(self, "lights", tuple(sorted(self.lights, key=lambda light: light.name)))
        if len({light.name for light in self.lights}) != len(self.lights):
            raise EditorLightingError22("duplicate light name")
        if not isinstance(self.environment, EnvironmentSpec22) or not isinstance(self.postfx, PostFXSpec22):
            raise EditorLightingError22("invalid environment or post-FX settings")
        _renderer_settings(self.renderer)
        if self.mode == "2d" and (self.lights or self.environment.enabled
                                 or self.environment.skybox_texture is not None):
            raise EditorLightingError22("2D profiles support post-FX only")
        if self.mode == "3d" and not self.postfx.enabled:
            raise EditorLightingError22("Renderer2 requires post-FX enabled; use neutral tone mapping")
        for kind in ("directional", "point", "spot"):
            count = sum(light.kind == kind for light in self.lights)
            count += 2 if kind == "directional" and self.environment.enabled else 0
            if count > 4:
                raise EditorLightingError22(f"{kind} light budget exceeds 4 (including environment)")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_serialize(asdict(self)).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LightingRuntime22:
    spec: SceneLightingSpec22
    lights: tuple[object, ...]
    skybox: Skybox3D | None

    def apply_to_game(self, game: Game) -> SceneMount:
        """Install before Game.run(); return explicit ownership for later unmounting."""
        if not isinstance(game, Game) or game.mode != self.spec.mode or game.running:
            raise EditorLightingError22("lighting requires a stopped Game with matching mode")
        if self.spec.mode == "3d":
            selection = select_lights((*game.scene.objects, *self.lights), default_directional=False)
            if selection.dropped:
                raise EditorLightingError22("scene lighting exceeds shipping light budgets")
        postfx = self.spec.postfx.runtime()
        renderer = Renderer2Settings(**asdict(self.spec.renderer))
        objects = self.lights if self.skybox is None else (*self.lights, self.skybox)
        if any(obj in game.scene for obj in objects):
            raise EditorLightingError22("lighting runtime is already installed in this scene")
        mount = game.scene.mount(*objects)
        game.configure_postprocess(**asdict(postfx))
        if self.spec.mode == "3d":
            game.configure_renderer2(**asdict(renderer))
            if self.skybox is not None:
                self.skybox.follow(game.camera)
        return mount


def _serialize(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EditorLightingError22(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


class EditorLightingTooling22:
    """Scene-keyed portable authoring data mapped to shipping lighting and post-FX."""

    relative_path = "config/lighting.json"

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self._profiles: dict[str, SceneLightingSpec22] = {}
        self._saved = self._serialized()
        if self.target.exists():
            self.load()

    @property
    def target(self) -> Path:
        return _contained(self.project_root, self.relative_path)

    @property
    def dirty(self) -> bool:
        return self._serialized() != self._saved

    def profiles(self) -> tuple[SceneLightingSpec22, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def require(self, scene: str) -> SceneLightingSpec22:
        key = _path(scene, "scene")
        try:
            return self._profiles[key]
        except KeyError as exc:
            raise EditorLightingError22(f"no lighting profile for {key!r}") from exc

    def set_profile(self, spec: SceneLightingSpec22) -> SceneLightingSpec22:
        if not isinstance(spec, SceneLightingSpec22):
            raise EditorLightingError22("profile must be SceneLightingSpec22")
        _contained(self.project_root, spec.scene)
        if spec.scene not in self._profiles and len(self._profiles) >= MAX_LIGHTING_SCENES:
            raise EditorLightingError22("too many scene lighting profiles")
        candidate = {**self._profiles, spec.scene: spec}
        if len(self._serialized(candidate).encode("utf-8")) > MAX_LIGHTING_BYTES:
            raise EditorLightingError22("lighting library exceeds byte budget")
        self._profiles = candidate
        return spec

    def update(self, scene: str, /, **changes: Any) -> SceneLightingSpec22:
        if "scene" in changes:
            raise EditorLightingError22("use remove/set to change scene binding")
        return self.set_profile(replace(self.require(scene), **changes))

    def remove(self, scene: str) -> None:
        del self._profiles[self.require(scene).scene]

    def build_runtime(self, scene: str) -> LightingRuntime22:
        spec = self.require(scene)
        _contained(self.project_root, spec.scene)
        env = spec.environment
        skybox = None
        if env.skybox_texture is not None:
            # Re-resolve every time: replacing assets/ with a symlink cannot escape the project.
            assets = _contained(self.project_root, "assets")
            texture = _contained(assets, env.skybox_texture)
            if not texture.is_file():
                raise EditorLightingError22(f"missing skybox texture: {env.skybox_texture}")
            if env.enabled:
                skybox = Skybox3D(texture, size=env.skybox_size, name="__lighting_skybox__")
        lights: tuple[object, ...] = tuple(light.runtime() for light in spec.lights)
        if env.enabled:
            rig = Environment3D(sky_color=Color(*env.sky_color), ground_color=Color(*env.ground_color),
                                intensity=env.intensity, ground_intensity=env.ground_intensity)
            lights += rig.lights()
        return LightingRuntime22(spec, lights, skybox)

    def _serialized(self, profiles: dict[str, SceneLightingSpec22] | None = None) -> str:
        data = self._profiles if profiles is None else profiles
        return _serialize(dict(format=LIGHTING_FORMAT, version=LIGHTING_VERSION,
                               profiles=[asdict(data[key]) for key in sorted(data)]))

    def save(self) -> None:
        data = self._serialized()
        for spec in self.profiles():
            _contained(self.project_root, spec.scene)
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.target
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                             dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved = data

    def load(self) -> None:
        try:
            with self.target.open("rb") as handle:
                raw = handle.read(MAX_LIGHTING_BYTES + 1)
            if len(raw) > MAX_LIGHTING_BYTES:
                raise EditorLightingError22("lighting library exceeds byte budget")
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(payload, dict) or set(payload) != {"format", "version", "profiles"}:
                raise EditorLightingError22("invalid lighting library schema")
            if (payload["format"] != LIGHTING_FORMAT or type(payload["version"]) is not int
                    or payload["version"] != LIGHTING_VERSION):
                raise EditorLightingError22("unsupported lighting library")
            entries = payload["profiles"]
            if not isinstance(entries, list) or len(entries) > MAX_LIGHTING_SCENES:
                raise EditorLightingError22("invalid lighting profile count")
            candidate: dict[str, SceneLightingSpec22] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise EditorLightingError22("lighting profile must be an object")
                entry = dict(entry)
                entry["lights"] = tuple(LightSpec22(**item) for item in entry.get("lights", []))
                entry["environment"] = EnvironmentSpec22(**entry.get("environment", {}))
                entry["postfx"] = PostFXSpec22(**entry.get("postfx", {}))
                entry["renderer"] = Renderer2Settings(**entry.get("renderer", {}))
                spec = SceneLightingSpec22(**entry)
                _contained(self.project_root, spec.scene)
                if spec.scene in candidate:
                    raise EditorLightingError22("duplicate scene lighting profile")
                candidate[spec.scene] = spec
            saved = self._serialized(candidate)
            if len(saved.encode("utf-8")) > MAX_LIGHTING_BYTES:
                raise EditorLightingError22("expanded lighting library exceeds byte budget")
        except (OSError, UnicodeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise EditorLightingError22(f"cannot load lighting library: {exc}") from exc
        self._profiles, self._saved = candidate, saved
