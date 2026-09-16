from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assets import AssetManager
from .audio import AudioBackend, AudioBus, AudioEngine, AudioHandle
from .math.types import Vec3


def _finite_float(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, _finite_float(value, label="volume")))


def _priority(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("audio priority must be an integer")
    if not 0 <= value <= 255:
        raise ValueError("audio priority must be between 0 and 255")
    return value


def _position(
    value: Vec3 | tuple[float, float, float],
) -> Vec3:
    if isinstance(value, Vec3):
        components = (value.x, value.y, value.z)
    else:
        if len(value) != 3:
            raise ValueError("audio position must contain exactly three values")
        components = value
    x, y, z = (
        _finite_float(component, label="audio position component")
        for component in components
    )
    return Vec3(x, y, z)


@dataclass(slots=True)
class HeadlessAudioToken:
    """In-memory audio token used by the deterministic headless backend."""

    voice_id: int
    path: Path
    volume: float
    loop: bool
    music: bool
    left: float | None = None
    right: float | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class HeadlessAudioEvent:
    sequence: int
    action: str
    voice_id: int | None
    asset: str | None
    volume: float | None = None
    left: float | None = None
    right: float | None = None
    loop: bool | None = None
    music: bool | None = None


class HeadlessAudioBackend:
    """Deterministic backend for tests, servers, replays and diagnostics."""

    def __init__(self) -> None:
        self._next_voice_id = 1
        self._sequence = 0
        self._tokens: dict[int, HeadlessAudioToken] = {}
        self._events: list[HeadlessAudioEvent] = []
        self._closed = False

    @property
    def events(self) -> tuple[HeadlessAudioEvent, ...]:
        return tuple(self._events)

    @property
    def active_tokens(self) -> tuple[HeadlessAudioToken, ...]:
        return tuple(
            token
            for _, token in sorted(self._tokens.items())
            if token.active
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def clear_events(self) -> None:
        self._events.clear()

    def _record(
        self,
        action: str,
        token: HeadlessAudioToken | None = None,
        *,
        volume: float | None = None,
        left: float | None = None,
        right: float | None = None,
    ) -> None:
        self._sequence += 1
        self._events.append(
            HeadlessAudioEvent(
                sequence=self._sequence,
                action=action,
                voice_id=token.voice_id if token is not None else None,
                asset=token.path.name if token is not None else None,
                volume=volume,
                left=left,
                right=right,
                loop=token.loop if token is not None else None,
                music=token.music if token is not None else None,
            )
        )

    def play(self, path: Path, *, volume: float, loop: bool, music: bool) -> object:
        if self._closed:
            raise RuntimeError("headless audio backend is closed")
        token = HeadlessAudioToken(
            voice_id=self._next_voice_id,
            path=Path(path),
            volume=_clamp_volume(volume),
            loop=bool(loop),
            music=bool(music),
        )
        self._next_voice_id += 1
        self._tokens[token.voice_id] = token
        self._record("play", token, volume=token.volume)
        return token

    def stop(self, token: object) -> None:
        if not isinstance(token, HeadlessAudioToken) or not token.active:
            return
        token.active = False
        self._record("stop", token)

    def set_volume(self, token: object, volume: float) -> None:
        if not isinstance(token, HeadlessAudioToken) or not token.active:
            return
        token.volume = _clamp_volume(volume)
        token.left = None
        token.right = None
        self._record("volume", token, volume=token.volume)

    def set_stereo(self, token: object, left: float, right: float) -> None:
        if not isinstance(token, HeadlessAudioToken) or not token.active:
            return
        token.left = _clamp_volume(left)
        token.right = _clamp_volume(right)
        token.volume = max(token.left, token.right)
        self._record("stereo", token, left=token.left, right=token.right)

    def stop_all(self) -> None:
        for token in tuple(self.active_tokens):
            self.stop(token)
        self._record("stop_all")

    def close(self) -> None:
        if self._closed:
            return
        self.stop_all()
        self._closed = True
        self._record("close")


@dataclass(frozen=True, slots=True)
class AudioSnapshotBus:
    """Target state for one bus inside an Audio 2.0 snapshot."""

    volume: float | None = None
    muted: bool | None = None

    def __post_init__(self) -> None:
        if self.volume is not None:
            object.__setattr__(self, "volume", _clamp_volume(self.volume))
        if self.muted is not None:
            object.__setattr__(self, "muted", bool(self.muted))


@dataclass(frozen=True, slots=True)
class AudioSnapshot:
    """Portable mixer snapshot with deterministic bus ordering."""

    name: str
    buses: tuple[tuple[str, AudioSnapshotBus], ...] = ()
    master_volume: float | None = None

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ValueError("audio snapshot name must not be empty")
        object.__setattr__(self, "name", name)
        if self.master_volume is not None:
            object.__setattr__(self, "master_volume", _clamp_volume(self.master_volume))

        normalized: dict[str, AudioSnapshotBus] = {}
        for bus_name, state in self.buses:
            bus_name = str(bus_name).strip()
            if not bus_name:
                raise ValueError("audio snapshot bus name must not be empty")
            if bus_name == "master":
                raise ValueError(
                    "audio snapshots use master_volume for the master bus; "
                    "do not include 'master' in buses"
                )
            if bus_name in normalized:
                raise ValueError(f"duplicate audio snapshot bus: {bus_name!r}")
            if not isinstance(state, AudioSnapshotBus):
                raise TypeError("audio snapshot bus values must be AudioSnapshotBus instances")
            normalized[bus_name] = state
        object.__setattr__(self, "buses", tuple(sorted(normalized.items())))

    @classmethod
    def from_mapping(
        cls,
        name: str,
        buses: Mapping[str, AudioSnapshotBus | Mapping[str, Any]],
        *,
        master_volume: float | None = None,
    ) -> AudioSnapshot:
        entries: list[tuple[str, AudioSnapshotBus]] = []
        for bus_name, state in buses.items():
            if isinstance(state, AudioSnapshotBus):
                normalized = state
            elif isinstance(state, Mapping):
                unknown = set(state) - {"volume", "muted"}
                if unknown:
                    raise ValueError(
                        f"unknown audio snapshot bus fields for {bus_name!r}: {sorted(unknown)}"
                    )
                normalized = AudioSnapshotBus(
                    volume=state.get("volume"),
                    muted=state.get("muted"),
                )
            else:
                raise TypeError("audio snapshot bus values must be mappings or AudioSnapshotBus")
            entries.append((str(bus_name), normalized))
        return cls(str(name), tuple(entries), master_volume)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "master_volume": self.master_volume,
            "buses": {
                name: {"volume": state.volume, "muted": state.muted}
                for name, state in self.buses
            },
        }


@dataclass(frozen=True, slots=True)
class AudioVoiceDiagnostics:
    voice_id: int
    asset: str
    priority: int
    protected: bool
    sequence: int
    bus: str
    volume: float
    pan: float
    loop: bool
    spatial_position: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class Audio2Diagnostics:
    active_voices: int
    max_voices: int
    stolen_voices: int
    rejected_voices: int
    current_snapshot: str | None
    transition_snapshot: str | None
    transition_progress: float | None
    master_volume: float
    buses: tuple[tuple[str, float, bool], ...]
    voices: tuple[AudioVoiceDiagnostics, ...]
    backend_events: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_voices": self.active_voices,
            "max_voices": self.max_voices,
            "stolen_voices": self.stolen_voices,
            "rejected_voices": self.rejected_voices,
            "current_snapshot": self.current_snapshot,
            "transition_snapshot": self.transition_snapshot,
            "transition_progress": self.transition_progress,
            "master_volume": self.master_volume,
            "buses": [
                {"name": name, "volume": volume, "muted": muted}
                for name, volume, muted in self.buses
            ],
            "voices": [
                {
                    "voice_id": voice.voice_id,
                    "asset": voice.asset,
                    "priority": voice.priority,
                    "protected": voice.protected,
                    "sequence": voice.sequence,
                    "bus": voice.bus,
                    "volume": voice.volume,
                    "pan": voice.pan,
                    "loop": voice.loop,
                    "spatial_position": (
                        list(voice.spatial_position)
                        if voice.spatial_position is not None
                        else None
                    ),
                }
                for voice in self.voices
            ],
            "backend_events": self.backend_events,
        }


@dataclass(slots=True)
class AudioVoice2:
    """Priority-aware creator handle layered over the stable 1.x AudioHandle."""

    _owner: AudioEngine2
    _handle: AudioHandle
    voice_id: int
    priority: int
    protected: bool
    sequence: int

    @property
    def active(self) -> bool:
        return self._handle.active

    @property
    def path(self) -> Path:
        return self._handle.path

    @property
    def bus(self) -> str:
        return self._handle.bus

    @property
    def volume(self) -> float:
        return self._handle.volume

    @property
    def pan(self) -> float:
        return self._handle.pan

    @property
    def loop(self) -> bool:
        return self._handle.loop

    @property
    def spatial_position(self) -> Vec3 | None:
        return self._handle.spatial_position

    def stop(self) -> None:
        self._owner.stop_voice(self)

    def set_priority(self, priority: int) -> AudioVoice2:
        self.priority = _priority(priority)
        return self

    def set_protected(self, protected: bool = True) -> AudioVoice2:
        self.protected = bool(protected)
        return self

    def set_volume(self, volume: float) -> AudioVoice2:
        self._handle.set_volume(_clamp_volume(volume))
        return self

    def set_bus(self, bus: str) -> AudioVoice2:
        self._handle.set_bus(bus)
        return self

    def set_pan(self, pan: float) -> AudioVoice2:
        pan = _finite_float(pan, label="audio pan")
        self._handle.set_pan(pan)
        return self

    def set_position(
        self,
        position: Vec3 | tuple[float, float, float],
        *,
        min_distance: float | None = None,
        max_distance: float | None = None,
    ) -> AudioVoice2:
        normalized = _position(position)
        if min_distance is not None:
            min_distance = _finite_float(min_distance, label="minimum audio distance")
        if max_distance is not None:
            max_distance = _finite_float(max_distance, label="maximum audio distance")
        self._handle.set_position(
            normalized,
            min_distance=min_distance,
            max_distance=max_distance,
        )
        return self

    def clear_position(self) -> AudioVoice2:
        self._handle.clear_position()
        return self

    def fade_to(self, volume: float, duration: float, *, stop: bool = False) -> AudioVoice2:
        duration = _finite_float(duration, label="audio fade duration")
        if duration < 0.0:
            raise ValueError("audio fade duration must not be negative")
        self._handle.fade_to(_clamp_volume(volume), duration, stop=stop)
        return self

    def fade_out(self, duration: float, *, stop: bool = True) -> AudioVoice2:
        return self.fade_to(0.0, duration, stop=stop)

    def fade_in(self, duration: float, *, target: float = 1.0) -> AudioVoice2:
        duration = _finite_float(duration, label="audio fade duration")
        if duration < 0.0:
            raise ValueError("audio fade duration must not be negative")
        self._handle.fade_in(duration, target=_clamp_volume(target))
        return self


@dataclass(slots=True)
class _SnapshotBusTransition:
    name: str
    start_volume: float
    target_volume: float
    target_muted: bool | None


@dataclass(slots=True)
class _SnapshotTransition:
    snapshot: AudioSnapshot
    duration: float
    elapsed: float
    start_master: float
    target_master: float
    buses: tuple[_SnapshotBusTransition, ...]


class AudioEngine2:
    """Opt-in SwirEngine 1.5 audio layer with budgets, snapshots and headless determinism."""

    def __init__(
        self,
        assets: AssetManager | str | Path = "assets",
        *,
        backend: AudioBackend | None = None,
        max_voices: int = 32,
    ) -> None:
        if not isinstance(max_voices, int) or isinstance(max_voices, bool):
            raise TypeError("max_voices must be an integer")
        if max_voices < 1:
            raise ValueError("max_voices must be at least 1")
        self.engine = AudioEngine(assets, backend=backend)
        self.max_voices = max_voices
        self._voices: dict[int, AudioVoice2] = {}
        self._next_voice_id = 1
        self._sequence = 0
        self._stolen_voices = 0
        self._rejected_voices = 0
        self._current_snapshot: str | None = None
        self._snapshot_transition: _SnapshotTransition | None = None

    @classmethod
    def headless(
        cls,
        assets: AssetManager | str | Path = "assets",
        *,
        max_voices: int = 32,
    ) -> AudioEngine2:
        return cls(assets, backend=HeadlessAudioBackend(), max_voices=max_voices)

    @property
    def backend(self) -> AudioBackend:
        return self.engine.backend

    @property
    def assets(self) -> AssetManager:
        return self.engine.assets

    @property
    def listener_position(self) -> Vec3:
        return self.engine.listener_position

    @property
    def voices(self) -> tuple[AudioVoice2, ...]:
        self._prune_voices()
        return tuple(self._voices[voice_id] for voice_id in sorted(self._voices))

    @property
    def current_snapshot(self) -> str | None:
        return self._current_snapshot

    @property
    def snapshot_transitioning(self) -> bool:
        return self._snapshot_transition is not None

    def ensure_bus(
        self,
        name: str,
        *,
        volume: float = 1.0,
        muted: bool = False,
    ) -> AudioBus:
        return self.engine.ensure_bus(name, volume=_clamp_volume(volume), muted=muted)

    def set_bus_volume(self, name: str, volume: float) -> AudioBus:
        return self.engine.set_bus_volume(name, _clamp_volume(volume))

    def mute_bus(self, name: str, muted: bool = True) -> AudioBus:
        return self.engine.mute_bus(name, muted)

    def set_listener_position(
        self,
        position: Vec3 | tuple[float, float, float],
    ) -> None:
        self.engine.set_listener_position(_position(position))

    def play(
        self,
        asset: str | Path,
        *,
        volume: float = 1.0,
        loop: bool = False,
        bus: str = "sfx",
        pan: float = 0.0,
        position: Vec3 | tuple[float, float, float] | None = None,
        min_distance: float = 1.0,
        max_distance: float = 30.0,
        fade_in: float = 0.0,
        priority: int = 128,
        protected: bool = False,
    ) -> AudioVoice2 | None:
        priority = _priority(priority)
        volume = _clamp_volume(volume)
        pan = _finite_float(pan, label="audio pan")
        min_distance = _finite_float(min_distance, label="minimum audio distance")
        max_distance = _finite_float(max_distance, label="maximum audio distance")
        fade_in = _finite_float(fade_in, label="audio fade duration")
        if min_distance < 0.0:
            raise ValueError("minimum audio distance must not be negative")
        if max_distance <= min_distance:
            raise ValueError("maximum audio distance must be greater than minimum distance")
        if fade_in < 0.0:
            raise ValueError("audio fade duration must not be negative")
        normalized_position = _position(position) if position is not None else None

        self._prune_voices()
        if len(self._voices) >= self.max_voices:
            victim = self._voice_to_steal(priority)
            if victim is None:
                self._rejected_voices += 1
                return None
            self.stop_voice(victim)
            self._stolen_voices += 1

        handle = self.engine.play(
            asset,
            volume=volume,
            loop=loop,
            bus=bus,
            pan=pan,
            position=normalized_position,
            min_distance=min_distance,
            max_distance=max_distance,
            fade_in=fade_in,
        )
        self._sequence += 1
        voice = AudioVoice2(
            self,
            handle,
            voice_id=self._next_voice_id,
            priority=priority,
            protected=bool(protected),
            sequence=self._sequence,
        )
        self._next_voice_id += 1
        self._voices[voice.voice_id] = voice
        return voice

    def music(
        self,
        asset: str | Path,
        *,
        volume: float = 1.0,
        loop: bool = True,
        bus: str = "music",
        fade_in: float = 0.0,
    ) -> AudioHandle:
        fade_in = _finite_float(fade_in, label="audio fade duration")
        if fade_in < 0.0:
            raise ValueError("audio fade duration must not be negative")
        return self.engine.music(
            asset,
            volume=_clamp_volume(volume),
            loop=loop,
            bus=bus,
            fade_in=fade_in,
        )

    def stop_music(self, *, fade_out: float = 0.0) -> None:
        fade_out = _finite_float(fade_out, label="audio fade duration")
        if fade_out < 0.0:
            raise ValueError("audio fade duration must not be negative")
        self.engine.stop_music(fade_out=fade_out)

    def stop_voice(self, voice: AudioVoice2) -> None:
        owned = self._voices.get(voice.voice_id)
        if owned is not voice:
            return
        voice._handle.stop()
        self._voices.pop(voice.voice_id, None)

    def stop_all(self) -> None:
        self.engine.stop_all()
        self._voices.clear()
        self._snapshot_transition = None

    def _voice_to_steal(self, incoming_priority: int) -> AudioVoice2 | None:
        candidates = [
            voice
            for voice in self._voices.values()
            if voice.active and not voice.protected and voice.priority <= incoming_priority
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda voice: (voice.priority, voice.sequence, voice.voice_id))

    def _prune_voices(self) -> None:
        stale = [voice_id for voice_id, voice in self._voices.items() if not voice.active]
        for voice_id in stale:
            self._voices.pop(voice_id, None)

    def capture_snapshot(
        self,
        name: str,
        *,
        buses: Sequence[str] | None = None,
        include_master: bool = True,
    ) -> AudioSnapshot:
        if buses is None:
            names = [bus.name for bus in self.engine.buses if bus.name != "master"]
        else:
            names = sorted({str(bus).strip() for bus in buses})
            if any(not name for name in names):
                raise ValueError("audio snapshot bus name must not be empty")
            if "master" in names:
                raise ValueError(
                    "capture the master bus through include_master/master_volume, "
                    "not through buses"
                )
        states = tuple(
            (
                name,
                AudioSnapshotBus(
                    volume=self.engine.bus(name).volume,
                    muted=self.engine.bus(name).muted,
                ),
            )
            for name in names
        )
        return AudioSnapshot(
            name=name,
            buses=states,
            master_volume=self.engine.master_volume if include_master else None,
        )

    def apply_snapshot(self, snapshot: AudioSnapshot, *, duration: float = 0.0) -> None:
        if not isinstance(snapshot, AudioSnapshot):
            raise TypeError("snapshot must be an AudioSnapshot")
        duration = _finite_float(duration, label="audio snapshot duration")
        if duration < 0.0:
            raise ValueError("audio snapshot duration must not be negative")

        transitions: list[_SnapshotBusTransition] = []
        for name, target in snapshot.buses:
            bus = self.engine.ensure_bus(name)
            if target.muted is False and bus.muted:
                self.engine.mute_bus(name, False)
            transitions.append(
                _SnapshotBusTransition(
                    name=name,
                    start_volume=bus.volume,
                    target_volume=bus.volume if target.volume is None else target.volume,
                    target_muted=target.muted,
                )
            )

        start_master = self.engine.master_volume
        target_master = (
            start_master if snapshot.master_volume is None else snapshot.master_volume
        )
        if duration == 0.0:
            self.engine.master_volume = target_master
            for transition in transitions:
                self.engine.set_bus_volume(transition.name, transition.target_volume)
                if transition.target_muted is not None:
                    self.engine.mute_bus(transition.name, transition.target_muted)
            self._snapshot_transition = None
            self._current_snapshot = snapshot.name
            return

        self._snapshot_transition = _SnapshotTransition(
            snapshot=snapshot,
            duration=duration,
            elapsed=0.0,
            start_master=start_master,
            target_master=target_master,
            buses=tuple(transitions),
        )
        self._current_snapshot = None

    def cancel_snapshot_transition(self) -> bool:
        if self._snapshot_transition is None:
            return False
        self._snapshot_transition = None
        return True

    def update(self, dt: float) -> None:
        dt = _finite_float(dt, label="audio update delta")
        if dt < 0.0:
            raise ValueError("audio update delta must not be negative")
        self._advance_snapshot(dt)
        self.engine.update(dt)
        self._prune_voices()

    def _advance_snapshot(self, dt: float) -> None:
        transition = self._snapshot_transition
        if transition is None:
            return
        transition.elapsed = min(transition.duration, transition.elapsed + dt)
        ratio = transition.elapsed / transition.duration
        self.engine.master_volume = transition.start_master + (
            transition.target_master - transition.start_master
        ) * ratio
        for bus_transition in transition.buses:
            volume = bus_transition.start_volume + (
                bus_transition.target_volume - bus_transition.start_volume
            ) * ratio
            self.engine.set_bus_volume(bus_transition.name, volume)
        if ratio < 1.0:
            return
        for bus_transition in transition.buses:
            if bus_transition.target_muted is not None:
                self.engine.mute_bus(
                    bus_transition.name,
                    bus_transition.target_muted,
                )
        self._current_snapshot = transition.snapshot.name
        self._snapshot_transition = None

    def diagnostics(self) -> Audio2Diagnostics:
        self._prune_voices()
        transition = self._snapshot_transition
        progress = None
        transition_name = None
        if transition is not None:
            transition_name = transition.snapshot.name
            progress = transition.elapsed / transition.duration

        root = self.assets.root.expanduser().resolve()

        def asset_key(path: Path) -> str:
            resolved = path.expanduser().resolve()
            try:
                return resolved.relative_to(root).as_posix()
            except ValueError:
                return resolved.name

        voices = tuple(
            AudioVoiceDiagnostics(
                voice_id=voice.voice_id,
                asset=asset_key(voice.path),
                priority=voice.priority,
                protected=voice.protected,
                sequence=voice.sequence,
                bus=voice.bus,
                volume=voice.volume,
                pan=voice.pan,
                loop=voice.loop,
                spatial_position=(
                    (
                        voice.spatial_position.x,
                        voice.spatial_position.y,
                        voice.spatial_position.z,
                    )
                    if voice.spatial_position is not None
                    else None
                ),
            )
            for voice in self.voices
        )
        buses = tuple(
            (bus.name, bus.volume, bus.muted)
            for bus in self.engine.buses
        )
        backend_events = (
            len(self.backend.events) if isinstance(self.backend, HeadlessAudioBackend) else 0
        )
        return Audio2Diagnostics(
            active_voices=len(voices),
            max_voices=self.max_voices,
            stolen_voices=self._stolen_voices,
            rejected_voices=self._rejected_voices,
            current_snapshot=self._current_snapshot,
            transition_snapshot=transition_name,
            transition_progress=progress,
            master_volume=self.engine.master_volume,
            buses=buses,
            voices=voices,
            backend_events=backend_events,
        )

    def state_fingerprint(self) -> str:
        payload = self.diagnostics().as_dict()
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def shutdown(self) -> None:
        self.engine.shutdown()
        self._voices.clear()
        self._snapshot_transition = None
