from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .assets import AssetManager, AssetReloadResult
from .audio import AudioEngine, AudioReloadEvent
from .filewatch import PluginAutoReloader, ReloadResult
from .graphics.live_assets import GPUTextureInvalidation, RendererAssetBridge

if TYPE_CHECKING:
    from typing_extensions import Self


@dataclass(frozen=True, slots=True)
class LiveDevelopmentResult:
    """One deterministic live-development polling transaction.

    A single result combines plugin source reloads, generic asset reloads, renderer GPU
    invalidations and audio restart/stop diagnostics. This gives editor/debug tooling one
    stable surface instead of forcing it to coordinate four independent histories.
    """

    plugin_reloads: tuple[ReloadResult, ...] = ()
    asset_reloads: tuple[AssetReloadResult, ...] = ()
    gpu_invalidations: tuple[GPUTextureInvalidation, ...] = ()
    audio_events: tuple[AudioReloadEvent, ...] = ()

    @property
    def changed(self) -> bool:
        return any(
            (
                self.plugin_reloads,
                self.asset_reloads,
                self.gpu_invalidations,
                self.audio_events,
            )
        )

    @property
    def healthy(self) -> bool:
        return not self.errors

    @property
    def errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        for result in self.plugin_reloads:
            if result.error:
                errors.append(f"plugin {result.plugin}: {result.error}")
        for result in self.asset_reloads:
            if result.error:
                errors.append(f"asset {result.path}: {result.error}")
        for event in self.audio_events:
            if event.error:
                errors.append(f"audio {event.path}: {event.error}")
        return tuple(errors)

    @property
    def event_count(self) -> int:
        return (
            len(self.plugin_reloads)
            + len(self.asset_reloads)
            + len(self.gpu_invalidations)
            + len(self.audio_events)
        )


class LiveDevelopmentHub:
    """Coordinate live plugin, asset, renderer and audio updates from one poll call.

    The hub intentionally owns no background thread. Call :meth:`poll` from an editor or game
    update loop. It polls plugin source files independently, then polls the shared ``AssetManager``
    exactly once so renderer and audio subscribers observe the same invalidation transaction.

    ``renderer_bridge`` and ``audio`` must use the same ``AssetManager`` passed to the hub. The
    hub can manage their live-reload subscriptions with :meth:`start`/:meth:`stop` and only tears
    down subscriptions that it activated itself.
    """

    def __init__(
        self,
        assets: AssetManager,
        *,
        plugin_reloader: PluginAutoReloader | None = None,
        renderer_bridge: RendererAssetBridge | None = None,
        audio: AudioEngine | None = None,
        scene_or_objects: object | None = None,
        reload_cached: bool = True,
        restart_one_shots: bool = False,
    ) -> None:
        if renderer_bridge is not None and renderer_bridge.assets is not assets:
            raise ValueError("renderer_bridge must use the hub AssetManager")
        if audio is not None and audio.assets is not assets:
            raise ValueError("audio must use the hub AssetManager")
        self.assets = assets
        self.plugin_reloader = plugin_reloader
        self.renderer_bridge = renderer_bridge
        self.audio = audio
        self.scene_or_objects = scene_or_objects
        self.reload_cached = bool(reload_cached)
        self.restart_one_shots = bool(restart_one_shots)
        self._started = False
        self._bound_renderer = False
        self._enabled_audio = False
        self._history: list[LiveDevelopmentResult] = []

    @property
    def started(self) -> bool:
        return self._started

    @property
    def history(self) -> tuple[LiveDevelopmentResult, ...]:
        return tuple(self._history)

    def start(self) -> Self:
        if self._started:
            return self
        if self.renderer_bridge is not None and not self.renderer_bridge.bound:
            self.renderer_bridge.bind()
            self._bound_renderer = True
        if self.audio is not None and not self.audio.live_reload_enabled:
            self.audio.enable_live_reload(restart_one_shots=self.restart_one_shots)
            self._enabled_audio = True
        self.sync_watches()
        self._started = True
        return self

    def stop(self) -> bool:
        if not self._started:
            return False
        if self._bound_renderer and self.renderer_bridge is not None:
            self.renderer_bridge.unbind()
        if self._enabled_audio and self.audio is not None:
            self.audio.disable_live_reload()
        self._bound_renderer = False
        self._enabled_audio = False
        self._started = False
        return True

    def sync_watches(self) -> tuple[object, ...]:
        """Refresh dynamic renderer/audio watches and return watched resources."""
        watched: list[object] = []
        if self.renderer_bridge is not None and self.scene_or_objects is not None:
            watched.extend(self.renderer_bridge.watch_scene_textures(self.scene_or_objects))
        if self.audio is not None:
            watched.extend(self.audio.watch_active())
        return tuple(watched)

    def poll(self) -> LiveDevelopmentResult:
        if not self._started:
            self.start()

        self.sync_watches()
        gpu_before = (
            len(self.renderer_bridge.invalidations) if self.renderer_bridge is not None else 0
        )
        audio_before = len(self.audio.reload_events) if self.audio is not None else 0

        plugin_results = (
            self.plugin_reloader.poll() if self.plugin_reloader is not None else ()
        )
        asset_results = self.assets.poll_changes(reload_cached=self.reload_cached)

        gpu_events = (
            self.renderer_bridge.invalidations[gpu_before:]
            if self.renderer_bridge is not None
            else ()
        )
        audio_events = (
            self.audio.reload_events[audio_before:] if self.audio is not None else ()
        )
        result = LiveDevelopmentResult(
            plugin_reloads=tuple(plugin_results),
            asset_reloads=tuple(asset_results),
            gpu_invalidations=tuple(gpu_events),
            audio_events=tuple(audio_events),
        )
        if result.changed:
            self._history.append(result)
        return result

    def clear_history(self, *, clear_subsystems: bool = False) -> None:
        self._history.clear()
        if not clear_subsystems:
            return
        if self.renderer_bridge is not None:
            self.renderer_bridge.clear_history()
        if self.audio is not None:
            self.audio.clear_reload_history()

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.stop()
