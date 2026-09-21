from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .animation15 import (
    AnimationClip,
    AnimationKeyframe,
    AnimationPose,
    AnimationTrack,
    InterpolationMode,
)

ANIMATION_ASSET_FORMAT = "swirengine-animation-clip"
ANIMATION_ASSET_VERSION = 1
DEFAULT_ANIMATION_DIRECTORY = "assets/animations"
_ANIMATION_SUFFIX = ".swiranim.json"
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")


class EditorAnimationToolingError(RuntimeError):
    """Raised when animation authoring cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class AnimationTrackSummary21:
    binding: str
    interpolation: str
    keyframe_count: int
    first_time: float
    last_time: float


@dataclass(frozen=True, slots=True)
class AnimationClipSnapshot21:
    path: str | None
    clip: AnimationClip | None
    loop: bool
    dirty: bool
    tracks: tuple[AnimationTrackSummary21, ...]

    @property
    def has_clip(self) -> bool:
        return self.clip is not None


def _project_relative(value: str | Path, *, label: str) -> PurePosixPath:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise EditorAnimationToolingError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorAnimationToolingError(f"{label} must stay project-relative")
    return posix


def _portable_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EditorAnimationToolingError("animation values must be finite")
        return value
    if isinstance(value, (tuple, list)):
        return [_portable_value(item) for item in value]
    raise EditorAnimationToolingError(
        f"unsupported animation value type: {type(value).__name__}"
    )


def _decode_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EditorAnimationToolingError("animation values must be finite")
        return value
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    raise EditorAnimationToolingError(
        f"unsupported animation value in asset: {type(value).__name__}"
    )


def _safe_asset_stem(name: str) -> str:
    clean = _SAFE_STEM.sub("-", name.strip()).strip("._-")
    if not clean:
        raise EditorAnimationToolingError("clip name must contain a usable filename")
    return clean.lower()


class EditorAnimationTooling21:
    """Project-bounded animation clip authoring backed by the 1.5 runtime API.

    Assets are deterministic JSON envelopes that compile directly to AnimationClip.
    The tooling intentionally reuses the shipping runtime model so editor preview and
    game playback sample the same tracks, interpolation and validation behavior.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        animation_directory: str | Path = DEFAULT_ANIMATION_DIRECTORY,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.animation_directory = _project_relative(
            animation_directory,
            label="animation directory",
        )
        self._path: PurePosixPath | None = None
        self._clip: AnimationClip | None = None
        self._loop = True
        self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def has_clip(self) -> bool:
        return self._clip is not None

    @property
    def clip(self) -> AnimationClip:
        if self._clip is None:
            raise EditorAnimationToolingError("no animation clip is open")
        return self._clip

    @property
    def loop(self) -> bool:
        return self._loop

    @property
    def relative_path(self) -> str | None:
        return None if self._path is None else self._path.as_posix()

    def snapshot(self) -> AnimationClipSnapshot21:
        tracks = ()
        if self._clip is not None:
            tracks = tuple(
                AnimationTrackSummary21(
                    binding=track.binding,
                    interpolation=track.interpolation.value,
                    keyframe_count=len(track.keyframes),
                    first_time=track.keyframes[0].time,
                    last_time=track.keyframes[-1].time,
                )
                for track in self._clip.tracks
            )
        return AnimationClipSnapshot21(
            path=self.relative_path,
            clip=self._clip,
            loop=self._loop,
            dirty=self._dirty,
            tracks=tracks,
        )

    def new_clip(
        self,
        name: str,
        *,
        duration: float = 1.0,
        loop: bool = True,
        path: str | Path | None = None,
    ) -> AnimationClipSnapshot21:
        clip = AnimationClip(name=name, duration=duration, tracks=())
        relative = (
            _project_relative(path, label="animation asset path")
            if path is not None
            else self.animation_directory / f"{_safe_asset_stem(clip.name)}{_ANIMATION_SUFFIX}"
        )
        self._validate_asset_suffix(relative)
        self._clip = clip
        self._loop = bool(loop)
        self._path = relative
        self._dirty = True
        return self.snapshot()

    def load(self, path: str | Path) -> AnimationClipSnapshot21:
        relative = _project_relative(path, label="animation asset path")
        self._validate_asset_suffix(relative)
        target = self._resolved_target(relative, require_exists=True)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorAnimationToolingError(
                f"cannot load animation asset {relative.as_posix()!r}: {exc}"
            ) from exc
        clip, loop = self._decode_asset(payload)
        self._path = relative
        self._clip = clip
        self._loop = loop
        self._dirty = False
        return self.snapshot()

    def reload(self) -> AnimationClipSnapshot21:
        if self._path is None:
            raise EditorAnimationToolingError("no animation asset path is available")
        return self.load(self._path)

    def save(self) -> AnimationClipSnapshot21:
        clip = self.clip
        if self._path is None:
            raise EditorAnimationToolingError("no animation asset path is available")
        target = self._resolved_target(self._path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Re-resolve after mkdir so a newly introduced symlink cannot redirect the write.
        target = self._resolved_target(self._path)
        payload = self._encode_asset(clip, loop=self._loop)
        try:
            target.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except (OSError, UnicodeError) as exc:
            raise EditorAnimationToolingError(
                f"cannot save animation asset {self._path.as_posix()!r}: {exc}"
            ) from exc
        self._dirty = False
        return self.snapshot()

    def rename_clip(self, name: str) -> AnimationClipSnapshot21:
        clip = self.clip
        self._replace_clip(AnimationClip(name=name, duration=clip.duration, tracks=clip.tracks))
        return self.snapshot()

    def set_duration(self, duration: float) -> AnimationClipSnapshot21:
        clip = self.clip
        self._replace_clip(AnimationClip(name=clip.name, duration=duration, tracks=clip.tracks))
        return self.snapshot()

    def set_loop(self, loop: bool) -> AnimationClipSnapshot21:
        loop = bool(loop)
        if loop != self._loop:
            self._loop = loop
            self._dirty = True
        return self.snapshot()

    def add_track(
        self,
        binding: str,
        *,
        initial_value: Any = 0.0,
        interpolation: InterpolationMode | str = InterpolationMode.LINEAR,
    ) -> AnimationClipSnapshot21:
        clip = self.clip
        binding = str(binding).strip()
        if any(track.binding == binding for track in clip.tracks):
            raise EditorAnimationToolingError(f"animation binding already exists: {binding!r}")
        track = AnimationTrack(
            binding=binding,
            keyframes=(AnimationKeyframe(0.0, _decode_value(_portable_value(initial_value))),),
            interpolation=interpolation,
        )
        self._replace_clip(
            AnimationClip(name=clip.name, duration=clip.duration, tracks=clip.tracks + (track,))
        )
        return self.snapshot()

    def remove_track(self, binding: str) -> AnimationClipSnapshot21:
        clip = self.clip
        tracks = tuple(track for track in clip.tracks if track.binding != binding)
        if len(tracks) == len(clip.tracks):
            raise EditorAnimationToolingError(f"unknown animation binding: {binding!r}")
        self._replace_clip(AnimationClip(name=clip.name, duration=clip.duration, tracks=tracks))
        return self.snapshot()

    def set_interpolation(
        self,
        binding: str,
        interpolation: InterpolationMode | str,
    ) -> AnimationClipSnapshot21:
        clip = self.clip
        tracks: list[AnimationTrack] = []
        found = False
        for track in clip.tracks:
            if track.binding == binding:
                found = True
                track = AnimationTrack(
                    binding=track.binding,
                    keyframes=track.keyframes,
                    interpolation=interpolation,
                )
            tracks.append(track)
        if not found:
            raise EditorAnimationToolingError(f"unknown animation binding: {binding!r}")
        self._replace_clip(AnimationClip(name=clip.name, duration=clip.duration, tracks=tuple(tracks)))
        return self.snapshot()

    def set_keyframe(
        self,
        binding: str,
        time: float,
        value: Any,
    ) -> AnimationClipSnapshot21:
        clip = self.clip
        time = float(time)
        if not math.isfinite(time) or time < 0.0:
            raise EditorAnimationToolingError("keyframe time must be finite and >= 0")
        if time > clip.duration:
            raise EditorAnimationToolingError("keyframe time must not exceed clip duration")
        value = _decode_value(_portable_value(value))
        tracks: list[AnimationTrack] = []
        found = False
        for track in clip.tracks:
            if track.binding != binding:
                tracks.append(track)
                continue
            found = True
            keyframes = [frame for frame in track.keyframes if frame.time != time]
            keyframes.append(AnimationKeyframe(time, value))
            keyframes.sort(key=lambda frame: frame.time)
            tracks.append(
                AnimationTrack(
                    binding=track.binding,
                    keyframes=tuple(keyframes),
                    interpolation=track.interpolation,
                )
            )
        if not found:
            raise EditorAnimationToolingError(f"unknown animation binding: {binding!r}")
        self._replace_clip(AnimationClip(name=clip.name, duration=clip.duration, tracks=tuple(tracks)))
        return self.snapshot()

    def remove_keyframe(self, binding: str, time: float) -> AnimationClipSnapshot21:
        clip = self.clip
        tracks: list[AnimationTrack] = []
        found_track = False
        found_keyframe = False
        for track in clip.tracks:
            if track.binding != binding:
                tracks.append(track)
                continue
            found_track = True
            keyframes = tuple(frame for frame in track.keyframes if frame.time != float(time))
            found_keyframe = len(keyframes) != len(track.keyframes)
            if not keyframes:
                raise EditorAnimationToolingError(
                    "a track must retain at least one keyframe; remove the track instead"
                )
            tracks.append(
                AnimationTrack(
                    binding=track.binding,
                    keyframes=keyframes,
                    interpolation=track.interpolation,
                )
            )
        if not found_track:
            raise EditorAnimationToolingError(f"unknown animation binding: {binding!r}")
        if not found_keyframe:
            raise EditorAnimationToolingError(
                f"no keyframe at {float(time):g} for binding {binding!r}"
            )
        self._replace_clip(AnimationClip(name=clip.name, duration=clip.duration, tracks=tuple(tracks)))
        return self.snapshot()

    def sample(self, time: float) -> AnimationPose:
        return self.clip.sample(time, loop=self._loop)

    def _replace_clip(self, clip: AnimationClip) -> None:
        self._clip = clip
        self._dirty = True

    def _validate_asset_suffix(self, relative: PurePosixPath) -> None:
        if not relative.as_posix().endswith(_ANIMATION_SUFFIX):
            raise EditorAnimationToolingError(
                f"animation assets must end with {_ANIMATION_SUFFIX!r}"
            )

    def _resolved_target(
        self,
        relative: PurePosixPath,
        *,
        require_exists: bool = False,
    ) -> Path:
        root = self.project_root
        target = root.joinpath(*relative.parts)
        resolved = target.resolve(strict=require_exists)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise EditorAnimationToolingError(
                f"animation asset path escapes the project root: {relative.as_posix()!r}"
            ) from exc
        return resolved

    @staticmethod
    def _encode_asset(clip: AnimationClip, *, loop: bool) -> dict[str, Any]:
        return {
            "format": ANIMATION_ASSET_FORMAT,
            "version": ANIMATION_ASSET_VERSION,
            "name": clip.name,
            "duration": clip.duration,
            "loop": bool(loop),
            "tracks": [
                {
                    "binding": track.binding,
                    "interpolation": track.interpolation.value,
                    "keyframes": [
                        {"time": frame.time, "value": _portable_value(frame.value)}
                        for frame in track.keyframes
                    ],
                }
                for track in clip.tracks
            ],
        }

    @staticmethod
    def _decode_asset(payload: Any) -> tuple[AnimationClip, bool]:
        if not isinstance(payload, dict):
            raise EditorAnimationToolingError("animation asset root must be an object")
        if payload.get("format") != ANIMATION_ASSET_FORMAT:
            raise EditorAnimationToolingError("unsupported animation asset format")
        if payload.get("version") != ANIMATION_ASSET_VERSION:
            raise EditorAnimationToolingError("unsupported animation asset version")
        tracks_payload = payload.get("tracks", [])
        if not isinstance(tracks_payload, list):
            raise EditorAnimationToolingError("animation tracks must be a list")
        tracks: list[AnimationTrack] = []
        try:
            for item in tracks_payload:
                if not isinstance(item, dict):
                    raise EditorAnimationToolingError("animation track entries must be objects")
                frames_payload = item.get("keyframes")
                if not isinstance(frames_payload, list) or not frames_payload:
                    raise EditorAnimationToolingError(
                        "animation tracks must contain at least one keyframe"
                    )
                frames = tuple(
                    AnimationKeyframe(
                        float(frame["time"]),
                        _decode_value(frame["value"]),
                    )
                    for frame in frames_payload
                    if isinstance(frame, dict)
                )
                if len(frames) != len(frames_payload):
                    raise EditorAnimationToolingError(
                        "animation keyframe entries must be objects"
                    )
                tracks.append(
                    AnimationTrack(
                        binding=str(item["binding"]),
                        keyframes=frames,
                        interpolation=str(item.get("interpolation", "linear")),
                    )
                )
            clip = AnimationClip(
                name=str(payload["name"]),
                duration=float(payload["duration"]),
                tracks=tuple(tracks),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EditorAnimationToolingError(f"invalid animation asset: {exc}") from exc
        loop = payload.get("loop", True)
        if not isinstance(loop, bool):
            raise EditorAnimationToolingError("animation loop flag must be bool")
        return clip, loop
