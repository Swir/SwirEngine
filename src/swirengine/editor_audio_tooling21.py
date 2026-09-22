from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .audio import AudioBackend, AudioEngine, AudioHandle

AUDIO_ASSET_FORMAT = "swirengine.audio-profile"
AUDIO_ASSET_VERSION = 1
DEFAULT_AUDIO_PATH = "config/audio.json"


class EditorAudioToolingError(ValueError):
    """Raised when project audio data cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class AudioBusSpec21:
    name: str
    volume: float = 1.0
    muted: bool = False

    def __post_init__(self) -> None:
        name = _name(self.name, "audio bus name")
        volume = _unit(self.volume, "audio bus volume")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "muted", bool(self.muted))


@dataclass(frozen=True, slots=True)
class AudioCueSpec21:
    name: str
    asset: str
    bus: str = "sfx"
    volume: float = 1.0
    loop: bool = False
    music: bool = False
    pan: float = 0.0
    position: tuple[float, float, float] | None = None
    min_distance: float = 1.0
    max_distance: float = 30.0
    fade_in: float = 0.0

    def __post_init__(self) -> None:
        name = _name(self.name, "audio cue name")
        asset = _asset_path(self.asset)
        bus = _name(self.bus, "audio cue bus")
        volume = _unit(self.volume, "audio cue volume")
        pan = _finite(self.pan, "audio cue pan")
        if pan < -1.0 or pan > 1.0:
            raise EditorAudioToolingError("audio cue pan must be between -1 and 1")
        position = None if self.position is None else _point(self.position, "audio cue position")
        min_distance = _non_negative(self.min_distance, "audio cue minimum distance")
        max_distance = _non_negative(self.max_distance, "audio cue maximum distance")
        if max_distance <= min_distance:
            raise EditorAudioToolingError("audio cue maximum distance must be greater than minimum distance")
        fade_in = _non_negative(self.fade_in, "audio cue fade-in")
        music = bool(self.music)
        if music and position is not None:
            raise EditorAudioToolingError("music cues cannot use a spatial position")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "asset", asset)
        object.__setattr__(self, "bus", bus)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "loop", bool(self.loop))
        object.__setattr__(self, "music", music)
        object.__setattr__(self, "pan", pan)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "min_distance", min_distance)
        object.__setattr__(self, "max_distance", max_distance)
        object.__setattr__(self, "fade_in", fade_in)


@dataclass(frozen=True, slots=True)
class EditorAudioSnapshot21:
    path: str
    buses: tuple[AudioBusSpec21, ...]
    cues: tuple[AudioCueSpec21, ...]
    dirty: bool


class EditorAudioTooling21:
    """Deterministic creator authoring over the shipping ``AudioEngine`` runtime."""

    def __init__(self, project_root: str | Path, *, path: str = DEFAULT_AUDIO_PATH) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.relative_path = _relative_path(path)
        self._buses: dict[str, AudioBusSpec21] = {
            "master": AudioBusSpec21("master"),
            "music": AudioBusSpec21("music"),
            "sfx": AudioBusSpec21("sfx"),
        }
        self._cues: dict[str, AudioCueSpec21] = {}
        self._saved_fingerprint = self._fingerprint()
        if self.target.is_file():
            self.load()

    @property
    def target(self) -> Path:
        return _target(self.project_root, self.relative_path)

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorAudioSnapshot21:
        return EditorAudioSnapshot21(
            self.relative_path,
            self._ordered_buses(),
            self._ordered_cues(),
            self.dirty,
        )

    def create_bus(self, name: str, *, volume: float = 1.0, muted: bool = False) -> EditorAudioSnapshot21:
        bus = AudioBusSpec21(name, volume, muted)
        if bus.name in self._buses:
            raise EditorAudioToolingError(f"audio bus {bus.name!r} already exists")
        self._buses[bus.name] = bus
        return self.snapshot()

    def update_bus(self, name: str, **changes: Any) -> EditorAudioSnapshot21:
        if "name" in changes:
            raise EditorAudioToolingError("audio bus name changes require remove/create")
        current = self._require_bus(name)
        updated = replace(current, **changes)
        self._buses[name] = updated
        return self.snapshot()

    def remove_bus(self, name: str) -> EditorAudioSnapshot21:
        if name in {"master", "sfx", "music"}:
            raise EditorAudioToolingError("built-in audio buses cannot be removed")
        self._require_bus(name)
        if any(cue.bus == name for cue in self._cues.values()):
            raise EditorAudioToolingError("move audio cues to another bus before removing it")
        del self._buses[name]
        return self.snapshot()

    def create_cue(self, name: str, asset: str, **settings: Any) -> EditorAudioSnapshot21:
        cue = AudioCueSpec21(name, asset, **settings)
        if cue.name in self._cues:
            raise EditorAudioToolingError(f"audio cue {cue.name!r} already exists")
        self._require_bus(cue.bus)
        self._cues[cue.name] = cue
        return self.snapshot()

    def update_cue(self, name: str, **changes: Any) -> EditorAudioSnapshot21:
        if "name" in changes:
            raise EditorAudioToolingError("audio cue name changes require remove/create")
        cue = replace(self._require_cue(name), **changes)
        self._require_bus(cue.bus)
        self._cues[name] = cue
        return self.snapshot()

    def remove_cue(self, name: str) -> EditorAudioSnapshot21:
        self._require_cue(name)
        del self._cues[name]
        return self.snapshot()

    def build_engine(self, *, backend: AudioBackend | None = None) -> AudioEngine:
        engine = AudioEngine(self.project_root / "assets", backend=backend)
        for spec in self._ordered_buses():
            engine.ensure_bus(spec.name)
            engine.set_bus_volume(spec.name, spec.volume)
            engine.mute_bus(spec.name, spec.muted)
        return engine

    def preview_cue(
        self,
        name: str,
        *,
        backend: AudioBackend | None = None,
    ) -> tuple[AudioEngine, AudioHandle]:
        cue = self._require_cue(name)
        engine = self.build_engine(backend=backend)
        try:
            if cue.music:
                handle = engine.music(
                    cue.asset,
                    volume=cue.volume,
                    loop=cue.loop,
                    bus=cue.bus,
                    fade_in=cue.fade_in,
                )
            else:
                handle = engine.play(
                    cue.asset,
                    volume=cue.volume,
                    loop=cue.loop,
                    bus=cue.bus,
                    pan=cue.pan,
                    position=cue.position,
                    min_distance=cue.min_distance,
                    max_distance=cue.max_distance,
                    fade_in=cue.fade_in,
                )
        except Exception:
            engine.shutdown()
            raise
        return engine, handle

    def save(self) -> EditorAudioSnapshot21:
        self._validate()
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=target.parent, delete=False
            ) as handle:
                handle.write(self._serialized_text())
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, self.target)
            temporary = None
        except OSError as exc:
            raise EditorAudioToolingError(f"cannot save audio configuration: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def load(self) -> EditorAudioSnapshot21:
        try:
            payload = json.loads(self.target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorAudioToolingError(f"cannot load audio configuration: {exc}") from exc
        buses, cues = _decode(payload)
        self._buses = _unique(buses, "bus")
        self._cues = _unique(cues, "cue")
        for required in ("master", "sfx", "music"):
            if required not in self._buses:
                raise EditorAudioToolingError(f"audio configuration is missing built-in bus {required!r}")
        self._validate()
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def _validate(self) -> None:
        for cue in self._cues.values():
            self._require_bus(cue.bus)

    def _require_bus(self, name: str) -> AudioBusSpec21:
        try:
            return self._buses[str(name)]
        except KeyError as exc:
            raise EditorAudioToolingError(f"unknown audio bus {name!r}") from exc

    def _require_cue(self, name: str) -> AudioCueSpec21:
        try:
            return self._cues[str(name)]
        except KeyError as exc:
            raise EditorAudioToolingError(f"unknown audio cue {name!r}") from exc

    def _ordered_buses(self) -> tuple[AudioBusSpec21, ...]:
        return tuple(self._buses[name] for name in sorted(self._buses))

    def _ordered_cues(self) -> tuple[AudioCueSpec21, ...]:
        return tuple(self._cues[name] for name in sorted(self._cues))

    def _payload(self) -> dict[str, Any]:
        return {
            "format": AUDIO_ASSET_FORMAT,
            "version": AUDIO_ASSET_VERSION,
            "buses": [asdict(item) for item in self._ordered_buses()],
            "cues": [asdict(item) for item in self._ordered_cues()],
        }

    def _serialized_text(self) -> str:
        return json.dumps(
            self._payload(), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        ) + "\n"

    def _fingerprint(self) -> str:
        encoded = json.dumps(
            self._payload(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def _decode(payload: Any) -> tuple[tuple[AudioBusSpec21, ...], tuple[AudioCueSpec21, ...]]:
    if not isinstance(payload, dict):
        raise EditorAudioToolingError("audio configuration must be an object")
    if set(payload) != {"format", "version", "buses", "cues"}:
        raise EditorAudioToolingError("audio configuration fields do not match schema")
    if payload["format"] != AUDIO_ASSET_FORMAT or payload["version"] != AUDIO_ASSET_VERSION:
        raise EditorAudioToolingError("unsupported audio configuration")
    return _items(payload["buses"], AudioBusSpec21, "buses"), _items(
        payload["cues"], AudioCueSpec21, "cues"
    )


def _items(value: Any, model: type[Any], label: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise EditorAudioToolingError(f"audio {label} must be an array")
    fields = set(model.__dataclass_fields__)
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) - fields:
            raise EditorAudioToolingError(f"invalid audio {label} entry")
        try:
            result.append(model(**item))
        except (TypeError, ValueError) as exc:
            raise EditorAudioToolingError(f"invalid audio {label} entry: {exc}") from exc
    return tuple(result)


def _unique(items: tuple[Any, ...], label: str) -> dict[str, Any]:
    result = {item.name: item for item in items}
    if len(result) != len(items):
        raise EditorAudioToolingError(f"duplicate audio {label} name")
    return result


def _name(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    value = value.strip()
    if not value:
        raise EditorAudioToolingError(f"{label} cannot be empty")
    return value


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EditorAudioToolingError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise EditorAudioToolingError(f"{label} must be finite")
    return result


def _unit(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0 or result > 1.0:
        raise EditorAudioToolingError(f"{label} must be between 0 and 1")
    return result


def _non_negative(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0:
        raise EditorAudioToolingError(f"{label} must not be negative")
    return result


def _point(value: Any, label: str) -> tuple[float, float, float]:
    if isinstance(value, (str, bytes)):
        raise EditorAudioToolingError(f"{label} must contain three values")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise EditorAudioToolingError(f"{label} must contain three numeric values") from exc
    if len(result) != 3 or not all(math.isfinite(item) for item in result):
        raise EditorAudioToolingError(f"{label} must contain three finite values")
    return result


def _asset_path(value: str | Path) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        not normalized
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
    ):
        raise EditorAudioToolingError("audio asset path must stay relative to the project assets directory")
    return posix.as_posix()


def _relative_path(value: str | Path) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        not normalized
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
    ):
        raise EditorAudioToolingError("audio configuration path must stay project-relative")
    return posix.as_posix()


def _target(root: Path, relative: str) -> Path:
    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorAudioToolingError("audio configuration path escapes the project root") from exc
    return resolved
