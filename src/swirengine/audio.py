from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Protocol

from .assets import AssetManager, AssetReloadResult
from .math.types import Vec3


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_pan(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


class AudioBackend(Protocol):
    def play(self, path: Path, *, volume: float, loop: bool, music: bool) -> object: ...

    def stop(self, token: object) -> None: ...

    def set_volume(self, token: object, volume: float) -> None: ...

    def stop_all(self) -> None: ...

    def close(self) -> None: ...


class PygameAudioBackend:
    """Lazy optional desktop audio backend powered by pygame.mixer."""

    def __init__(self) -> None:
        self._pygame = None
        self._music_token = object()

    def _module(self):
        if self._pygame is None:
            try:
                import pygame
            except ImportError as exc:
                raise RuntimeError(
                    'Audio support requires the optional dependency. '
                    'Install it with: python -m pip install "swirengine[audio]"'
                ) from exc
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._pygame = pygame
        return self._pygame

    def play(self, path: Path, *, volume: float, loop: bool, music: bool) -> object:
        pygame = self._module()
        loops = -1 if loop else 0
        if music:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(loops=loops)
            return self._music_token

        sound = pygame.mixer.Sound(str(path))
        channel = sound.play(loops=loops)
        if channel is None:
            raise RuntimeError("No free audio mixer channel is available")
        channel.set_volume(volume)
        return channel

    def stop(self, token: object) -> None:
        if self._pygame is None:
            return
        if token is self._music_token:
            self._pygame.mixer.music.stop()
            return
        stop = getattr(token, "stop", None)
        if callable(stop):
            stop()

    def set_volume(self, token: object, volume: float) -> None:
        if self._pygame is None:
            return
        if token is self._music_token:
            self._pygame.mixer.music.set_volume(volume)
            return
        setter = getattr(token, "set_volume", None)
        if callable(setter):
            setter(volume)

    def set_stereo(self, token: object, left: float, right: float) -> None:
        """Apply per-channel stereo gain when the backend token supports it."""
        if self._pygame is None or token is self._music_token:
            return
        setter = getattr(token, "set_volume", None)
        if callable(setter):
            setter(_clamp_volume(left), _clamp_volume(right))

    def stop_all(self) -> None:
        if self._pygame is None:
            return
        self._pygame.mixer.stop()
        self._pygame.mixer.music.stop()

    def close(self) -> None:
        if self._pygame is None:
            return
        self.stop_all()
        if self._pygame.mixer.get_init():
            self._pygame.mixer.quit()
        self._pygame = None


@dataclass(slots=True)
class AudioBus:
    """Creator-facing mixer bus used to group sounds under one gain/mute control."""

    name: str
    volume: float = 1.0
    muted: bool = False

    def set_volume(self, volume: float) -> AudioBus:
        self.volume = _clamp_volume(volume)
        return self


@dataclass(frozen=True, slots=True)
class AudioDiagnostics:
    active_handles: int
    active_music: int
    active_spatial: int
    fading_handles: int
    buses: tuple[str, ...]
    muted_buses: tuple[str, ...]
    master_volume: float


@dataclass(slots=True)
class AudioHandle:
    _engine: AudioEngine
    _token: object
    path: Path
    is_music: bool
    loop: bool
    _volume: float
    bus: str
    active: bool = True
    pan: float = 0.0
    spatial_position: Vec3 | None = None
    min_distance: float = 1.0
    max_distance: float = 30.0
    _fade_start: float | None = None
    _fade_target: float | None = None
    _fade_duration: float = 0.0
    _fade_elapsed: float = 0.0
    _stop_after_fade: bool = False

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def fading(self) -> bool:
        return self._fade_target is not None

    def set_volume(self, volume: float) -> AudioHandle:
        self._volume = _clamp_volume(volume)
        self._clear_fade()
        if self.active:
            self._engine._refresh(self)
        return self

    def set_bus(self, bus: str) -> AudioHandle:
        self._engine.ensure_bus(bus)
        self.bus = str(bus)
        if self.active:
            self._engine._refresh(self)
        return self

    def set_pan(self, pan: float) -> AudioHandle:
        self.pan = _clamp_pan(pan)
        if self.active:
            self._engine._refresh(self)
        return self

    def set_position(
        self,
        position: Vec3 | tuple[float, float, float],
        *,
        min_distance: float | None = None,
        max_distance: float | None = None,
    ) -> AudioHandle:
        if not isinstance(position, Vec3):
            position = Vec3(*map(float, position))
        self.spatial_position = position
        if min_distance is not None:
            self.min_distance = max(0.0, float(min_distance))
        if max_distance is not None:
            self.max_distance = max(self.min_distance + 1e-6, float(max_distance))
        if self.active:
            self._engine._refresh(self)
        return self

    def clear_position(self) -> AudioHandle:
        self.spatial_position = None
        if self.active:
            self._engine._refresh(self)
        return self

    def fade_to(self, volume: float, duration: float, *, stop: bool = False) -> AudioHandle:
        target = _clamp_volume(volume)
        duration = max(0.0, float(duration))
        if duration == 0.0:
            self._volume = target
            self._clear_fade()
            if self.active:
                self._engine._refresh(self)
                if stop:
                    self.stop()
            return self
        self._fade_start = self._volume
        self._fade_target = target
        self._fade_duration = duration
        self._fade_elapsed = 0.0
        self._stop_after_fade = bool(stop)
        return self

    def fade_out(self, duration: float, *, stop: bool = True) -> AudioHandle:
        return self.fade_to(0.0, duration, stop=stop)

    def fade_in(self, duration: float, *, target: float = 1.0) -> AudioHandle:
        self._volume = 0.0
        if self.active:
            self._engine._refresh(self)
        return self.fade_to(target, duration)

    def stop(self) -> None:
        if self.active:
            self._engine._stop(self)

    def _clear_fade(self) -> None:
        self._fade_start = None
        self._fade_target = None
        self._fade_duration = 0.0
        self._fade_elapsed = 0.0
        self._stop_after_fade = False


@dataclass(frozen=True, slots=True)
class AudioReloadEvent:
    """Diagnostic record produced when a watched audio asset is invalidated."""

    path: Path
    restarted: int
    stopped: int
    skipped: int
    error: str | None = None

    @property
    def affected(self) -> int:
        return self.restarted + self.stopped + self.skipped


class AudioEngine:
    """Creator-facing audio service with buses, fades, spatial gain and diagnostics."""

    def __init__(
        self,
        assets: AssetManager | str | Path = "assets",
        *,
        backend: AudioBackend | None = None,
    ) -> None:
        self.assets = assets if isinstance(assets, AssetManager) else AssetManager(assets)
        self.backend: AudioBackend = backend or PygameAudioBackend()
        self._master_volume = 1.0
        self._sound_volume = 1.0
        self._music_volume = 1.0
        self._handles: list[AudioHandle] = []
        self._music: AudioHandle | None = None
        self._buses: dict[str, AudioBus] = {
            "master": AudioBus("master"),
            "sfx": AudioBus("sfx"),
            "music": AudioBus("music"),
        }
        self._listener_position = Vec3(0.0, 0.0, 0.0)
        self._live_reload_enabled = False
        self._restart_one_shots = False
        self._reload_events: list[AudioReloadEvent] = []

    @property
    def master_volume(self) -> float:
        return self._master_volume

    @master_volume.setter
    def master_volume(self, value: float) -> None:
        self._master_volume = _clamp_volume(value)
        self._buses["master"].volume = self._master_volume
        self._refresh_all()

    @property
    def sound_volume(self) -> float:
        return self._sound_volume

    @sound_volume.setter
    def sound_volume(self, value: float) -> None:
        self._sound_volume = _clamp_volume(value)
        self._buses["sfx"].volume = self._sound_volume
        self._refresh_all(music=False)

    @property
    def music_volume(self) -> float:
        return self._music_volume

    @music_volume.setter
    def music_volume(self, value: float) -> None:
        self._music_volume = _clamp_volume(value)
        self._buses["music"].volume = self._music_volume
        self._refresh_all(music=True)

    @property
    def listener_position(self) -> Vec3:
        return self._listener_position

    @property
    def current_music(self) -> AudioHandle | None:
        return self._music if self._music is not None and self._music.active else None

    @property
    def active_handles(self) -> tuple[AudioHandle, ...]:
        return tuple(handle for handle in self._handles if handle.active)

    @property
    def buses(self) -> tuple[AudioBus, ...]:
        return tuple(self._buses[name] for name in sorted(self._buses))

    @property
    def live_reload_enabled(self) -> bool:
        return self._live_reload_enabled

    @property
    def restart_one_shots(self) -> bool:
        return self._restart_one_shots

    @property
    def reload_events(self) -> tuple[AudioReloadEvent, ...]:
        return tuple(self._reload_events)

    def ensure_bus(self, name: str, *, volume: float = 1.0, muted: bool = False) -> AudioBus:
        name = str(name).strip()
        if not name:
            raise ValueError("Audio bus name must not be empty")
        bus = self._buses.get(name)
        if bus is None:
            bus = AudioBus(name, _clamp_volume(volume), bool(muted))
            self._buses[name] = bus
        return bus

    def bus(self, name: str) -> AudioBus:
        try:
            return self._buses[str(name)]
        except KeyError as exc:
            raise KeyError(f"Unknown audio bus: {name!r}") from exc

    def set_bus_volume(self, name: str, volume: float) -> AudioBus:
        bus = self.ensure_bus(name)
        bus.volume = _clamp_volume(volume)
        if name == "master":
            self._master_volume = bus.volume
        elif name == "sfx":
            self._sound_volume = bus.volume
        elif name == "music":
            self._music_volume = bus.volume
        self._refresh_all()
        return bus

    def mute_bus(self, name: str, muted: bool = True) -> AudioBus:
        bus = self.ensure_bus(name)
        bus.muted = bool(muted)
        self._refresh_all()
        return bus

    def set_listener_position(self, position: Vec3 | tuple[float, float, float]) -> None:
        if not isinstance(position, Vec3):
            position = Vec3(*map(float, position))
        self._listener_position = position
        self._refresh_all()

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
    ) -> AudioHandle:
        return self._start(
            asset,
            volume=volume,
            loop=loop,
            music=False,
            bus=bus,
            pan=pan,
            position=position,
            min_distance=min_distance,
            max_distance=max_distance,
            fade_in=fade_in,
        )

    def music(
        self,
        asset: str | Path,
        *,
        volume: float = 1.0,
        loop: bool = True,
        bus: str = "music",
        fade_in: float = 0.0,
    ) -> AudioHandle:
        if self._music is not None and self._music.active:
            self._music.stop()
        handle = self._start(
            asset,
            volume=volume,
            loop=loop,
            music=True,
            bus=bus,
            pan=0.0,
            position=None,
            min_distance=1.0,
            max_distance=30.0,
            fade_in=fade_in,
        )
        self._music = handle
        return handle

    def stop_music(self, *, fade_out: float = 0.0) -> None:
        if self._music is not None and self._music.active:
            if fade_out > 0.0:
                self._music.fade_out(fade_out, stop=True)
            else:
                self._music.stop()

    def stop_all(self) -> None:
        self.backend.stop_all()
        for handle in self._handles:
            handle.active = False
            handle._clear_fade()
        self._handles.clear()
        self._music = None

    def update(self, dt: float) -> None:
        """Advance fades and refresh spatialized handles once per gameplay frame."""
        dt = max(0.0, float(dt))
        for handle in tuple(self._handles):
            if not handle.active:
                continue
            if handle.fading:
                assert handle._fade_start is not None
                assert handle._fade_target is not None
                handle._fade_elapsed += dt
                ratio = min(1.0, handle._fade_elapsed / handle._fade_duration)
                handle._volume = handle._fade_start + (
                    handle._fade_target - handle._fade_start
                ) * ratio
                self._refresh(handle)
                if ratio >= 1.0:
                    should_stop = handle._stop_after_fade
                    handle._clear_fade()
                    if should_stop:
                        handle.stop()
                        continue
            elif handle.spatial_position is not None:
                self._refresh(handle)

    def diagnostics(self) -> AudioDiagnostics:
        handles = self.active_handles
        return AudioDiagnostics(
            active_handles=len(handles),
            active_music=sum(handle.is_music for handle in handles),
            active_spatial=sum(handle.spatial_position is not None for handle in handles),
            fading_handles=sum(handle.fading for handle in handles),
            buses=tuple(sorted(self._buses)),
            muted_buses=tuple(sorted(name for name, bus in self._buses.items() if bus.muted)),
            master_volume=self._master_volume,
        )

    def enable_live_reload(self, *, restart_one_shots: bool = False) -> AudioEngine:
        """Watch active audio and react to ``AssetManager`` invalidations."""
        self._restart_one_shots = bool(restart_one_shots)
        if not self._live_reload_enabled:
            self.assets.add_invalidator(self._on_asset_invalidated)
            self._live_reload_enabled = True
        self.watch_active()
        return self

    def disable_live_reload(self) -> bool:
        if not self._live_reload_enabled:
            return False
        self.assets.remove_invalidator(self._on_asset_invalidated)
        self._live_reload_enabled = False
        return True

    def watch_active(self) -> tuple[Path, ...]:
        """Add all currently active audio files to the shared asset watcher."""
        paths = sorted(
            {handle.path.expanduser().resolve() for handle in self._handles if handle.active},
            key=lambda path: path.as_posix().lower(),
        )
        for path in paths:
            self.assets.watcher.watch(path)
        return tuple(paths)

    def poll_live_reload(self) -> tuple[AssetReloadResult, ...]:
        """Poll the shared watcher and dispatch invalidations to audio and other subscribers."""
        if not self._live_reload_enabled:
            return ()
        self.watch_active()
        return self.assets.poll_changes(reload_cached=True)

    def clear_reload_history(self) -> None:
        self._reload_events.clear()

    def shutdown(self) -> None:
        self.disable_live_reload()
        self.stop_all()
        self.backend.close()

    def _start(
        self,
        asset: str | Path,
        *,
        volume: float,
        loop: bool,
        music: bool,
        bus: str,
        pan: float,
        position: Vec3 | tuple[float, float, float] | None,
        min_distance: float,
        max_distance: float,
        fade_in: float,
    ) -> AudioHandle:
        path = self.assets.require(asset)
        self.ensure_bus(bus)
        local_volume = _clamp_volume(volume)
        if position is not None and not isinstance(position, Vec3):
            position = Vec3(*map(float, position))
        min_distance = max(0.0, float(min_distance))
        max_distance = max(min_distance + 1e-6, float(max_distance))
        initial_volume = 0.0 if fade_in > 0.0 else local_volume
        token = self.backend.play(
            path,
            volume=self._base_effective_volume(initial_volume, music, bus),
            loop=bool(loop),
            music=music,
        )
        handle = AudioHandle(
            self,
            token,
            path,
            music,
            bool(loop),
            initial_volume,
            bus,
            pan=_clamp_pan(pan),
            spatial_position=position,
            min_distance=min_distance,
            max_distance=max_distance,
        )
        self._handles.append(handle)
        if fade_in > 0.0:
            handle.fade_to(local_volume, fade_in)
        else:
            self._refresh(handle)
        if self._live_reload_enabled:
            self.assets.watcher.watch(path)
        return handle

    def _distance_gain(self, handle: AudioHandle) -> float:
        position = handle.spatial_position
        if position is None:
            return 1.0
        dx = position.x - self._listener_position.x
        dy = position.y - self._listener_position.y
        dz = position.z - self._listener_position.z
        distance = sqrt(dx * dx + dy * dy + dz * dz)
        if distance <= handle.min_distance:
            return 1.0
        if distance >= handle.max_distance:
            return 0.0
        span = handle.max_distance - handle.min_distance
        return 1.0 - ((distance - handle.min_distance) / span)

    def _spatial_pan(self, handle: AudioHandle) -> float:
        position = handle.spatial_position
        if position is None:
            return handle.pan
        span = max(handle.max_distance, 1e-6)
        relative_x = (position.x - self._listener_position.x) / span
        return _clamp_pan(handle.pan + relative_x)

    def _base_effective_volume(self, local_volume: float, music: bool, bus_name: str) -> float:
        category = self._music_volume if music else self._sound_volume
        bus = self.ensure_bus(bus_name)
        bus_gain = 0.0 if bus.muted else bus.volume
        master_bus = self._buses["master"]
        master_gain = 0.0 if master_bus.muted else self._master_volume
        gain = local_volume * category * master_gain
        if bus_name not in {"master", "sfx", "music"}:
            gain *= bus_gain
        return _clamp_volume(gain)

    def _handle_effective_volume(self, handle: AudioHandle) -> float:
        gain = self._base_effective_volume(handle.volume, handle.is_music, handle.bus)
        gain *= self._distance_gain(handle)
        return _clamp_volume(gain)

    def _refresh(self, handle: AudioHandle) -> None:
        volume = self._handle_effective_volume(handle)
        pan = self._spatial_pan(handle)
        stereo = getattr(self.backend, "set_stereo", None)
        if callable(stereo) and not handle.is_music and abs(pan) > 1e-9:
            left = volume * (1.0 - max(0.0, pan))
            right = volume * (1.0 + min(0.0, pan))
            stereo(handle._token, left, right)
            return
        self.backend.set_volume(handle._token, volume)

    def _refresh_all(self, music: bool | None = None) -> None:
        for handle in self._handles:
            if handle.active and (music is None or handle.is_music is music):
                self._refresh(handle)

    def _stop(self, handle: AudioHandle) -> None:
        self.backend.stop(handle._token)
        handle.active = False
        handle._clear_fade()
        if self._music is handle:
            self._music = None
        self._handles = [item for item in self._handles if item is not handle]

    def _on_asset_invalidated(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        matching = [
            handle
            for handle in self._handles
            if handle.active and handle.path.expanduser().resolve() == resolved
        ]
        if not matching:
            return

        restarted = 0
        stopped = 0
        skipped = 0
        errors: list[str] = []
        exists = resolved.exists()

        for handle in matching:
            should_restart = exists and (handle.is_music or handle.loop or self._restart_one_shots)
            if exists and not should_restart:
                skipped += 1
                continue

            try:
                self.backend.stop(handle._token)
            except Exception as exc:  # noqa: BLE001 - third-party audio backends may raise anything.
                errors.append(f"stop failed: {exc}")
                continue

            if not exists:
                handle.active = False
                stopped += 1
                if self._music is handle:
                    self._music = None
                continue

            try:
                handle._token = self.backend.play(
                    resolved,
                    volume=self._handle_effective_volume(handle),
                    loop=handle.loop,
                    music=handle.is_music,
                )
            except Exception as exc:  # noqa: BLE001 - third-party audio backends may raise anything.
                handle.active = False
                errors.append(f"restart failed: {exc}")
                if self._music is handle:
                    self._music = None
            else:
                restarted += 1
                self._refresh(handle)

        self._handles = [handle for handle in self._handles if handle.active]
        self._reload_events.append(
            AudioReloadEvent(
                path=resolved,
                restarted=restarted,
                stopped=stopped,
                skipped=skipped,
                error="; ".join(errors) if errors else None,
            )
        )
