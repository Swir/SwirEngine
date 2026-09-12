from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .assets import AssetManager, AssetReloadResult


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


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
class AudioHandle:
    _engine: AudioEngine
    _token: object
    path: Path
    is_music: bool
    loop: bool
    _volume: float
    active: bool = True

    @property
    def volume(self) -> float:
        return self._volume

    def set_volume(self, volume: float) -> AudioHandle:
        self._volume = _clamp_volume(volume)
        if self.active:
            self._engine._refresh(self)
        return self

    def stop(self) -> None:
        if self.active:
            self._engine._stop(self)


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
    """Small creator-facing audio service with pluggable playback backends."""

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
        self._live_reload_enabled = False
        self._restart_one_shots = False
        self._reload_events: list[AudioReloadEvent] = []

    @property
    def master_volume(self) -> float:
        return self._master_volume

    @master_volume.setter
    def master_volume(self, value: float) -> None:
        self._master_volume = _clamp_volume(value)
        self._refresh_all()

    @property
    def sound_volume(self) -> float:
        return self._sound_volume

    @sound_volume.setter
    def sound_volume(self, value: float) -> None:
        self._sound_volume = _clamp_volume(value)
        self._refresh_all(music=False)

    @property
    def music_volume(self) -> float:
        return self._music_volume

    @music_volume.setter
    def music_volume(self, value: float) -> None:
        self._music_volume = _clamp_volume(value)
        self._refresh_all(music=True)

    @property
    def current_music(self) -> AudioHandle | None:
        return self._music if self._music is not None and self._music.active else None

    @property
    def active_handles(self) -> tuple[AudioHandle, ...]:
        return tuple(handle for handle in self._handles if handle.active)

    @property
    def live_reload_enabled(self) -> bool:
        return self._live_reload_enabled

    @property
    def restart_one_shots(self) -> bool:
        return self._restart_one_shots

    @property
    def reload_events(self) -> tuple[AudioReloadEvent, ...]:
        return tuple(self._reload_events)

    def play(self, asset: str | Path, *, volume: float = 1.0, loop: bool = False) -> AudioHandle:
        return self._start(asset, volume=volume, loop=loop, music=False)

    def music(self, asset: str | Path, *, volume: float = 1.0, loop: bool = True) -> AudioHandle:
        if self._music is not None and self._music.active:
            self._music.stop()
        handle = self._start(asset, volume=volume, loop=loop, music=True)
        self._music = handle
        return handle

    def stop_music(self) -> None:
        if self._music is not None and self._music.active:
            self._music.stop()

    def stop_all(self) -> None:
        self.backend.stop_all()
        for handle in self._handles:
            handle.active = False
        self._handles.clear()
        self._music = None

    def enable_live_reload(self, *, restart_one_shots: bool = False) -> AudioEngine:
        """Watch active audio and react to ``AssetManager`` invalidations.

        Looping sounds and music are restarted in place by default. One-shot effects are left
        untouched unless ``restart_one_shots=True`` because replaying a short effect after an edit
        is usually more surprising than useful.
        """
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
    ) -> AudioHandle:
        path = self.assets.require(asset)
        local_volume = _clamp_volume(volume)
        token = self.backend.play(
            path,
            volume=self._effective_volume(local_volume, music),
            loop=bool(loop),
            music=music,
        )
        handle = AudioHandle(self, token, path, music, bool(loop), local_volume)
        self._handles.append(handle)
        if self._live_reload_enabled:
            self.assets.watcher.watch(path)
        return handle

    def _effective_volume(self, local_volume: float, music: bool) -> float:
        category = self._music_volume if music else self._sound_volume
        return _clamp_volume(local_volume * category * self._master_volume)

    def _refresh(self, handle: AudioHandle) -> None:
        self.backend.set_volume(
            handle._token,
            self._effective_volume(handle.volume, handle.is_music),
        )

    def _refresh_all(self, music: bool | None = None) -> None:
        for handle in self._handles:
            if handle.active and (music is None or handle.is_music is music):
                self._refresh(handle)

    def _stop(self, handle: AudioHandle) -> None:
        self.backend.stop(handle._token)
        handle.active = False
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
                    volume=self._effective_volume(handle.volume, handle.is_music),
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
