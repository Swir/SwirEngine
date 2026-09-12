from pathlib import Path

import pytest

from swirengine import AssetManager, AudioEngine
from swirengine.filewatch import ReloadResult
from swirengine.graphics.live_assets import RendererAssetBridge
from swirengine.live_development import LiveDevelopmentHub, LiveDevelopmentResult


class FakeTexture:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeRenderer:
    def __init__(self) -> None:
        self._textures = {}


class FakeAudioBackend:
    def __init__(self) -> None:
        self.plays = []
        self.stops = []

    def play(self, path: Path, *, volume: float, loop: bool, music: bool) -> object:
        token = object()
        self.plays.append((path, volume, loop, music, token))
        return token

    def stop(self, token: object) -> None:
        self.stops.append(token)

    def set_volume(self, _token: object, _volume: float) -> None:
        pass

    def stop_all(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakePluginReloader:
    def __init__(self, *results: ReloadResult) -> None:
        self.results = tuple(results)
        self.polls = 0

    def poll(self):
        self.polls += 1
        results, self.results = self.results, ()
        return results


def test_live_development_result_aggregates_health_and_counts(tmp_path):
    result = LiveDevelopmentResult(
        plugin_reloads=(ReloadResult("broken", tmp_path / "plugin.py", False, "boom"),),
    )

    assert result.changed
    assert result.event_count == 1
    assert not result.healthy
    assert result.errors == ("plugin broken: boom",)
    assert not LiveDevelopmentResult().changed
    assert LiveDevelopmentResult().healthy


def test_hub_rejects_renderer_or_audio_using_another_asset_manager(tmp_path):
    assets = AssetManager(tmp_path / "a")
    other = AssetManager(tmp_path / "b")
    bridge = RendererAssetBridge(FakeRenderer(), other)
    audio = AudioEngine(other, backend=FakeAudioBackend())

    with pytest.raises(ValueError, match="renderer_bridge"):
        LiveDevelopmentHub(assets, renderer_bridge=bridge)
    with pytest.raises(ValueError, match="audio"):
        LiveDevelopmentHub(assets, audio=audio)


def test_hub_manages_only_subscriptions_it_started(tmp_path):
    assets = AssetManager(tmp_path)
    bridge = RendererAssetBridge(FakeRenderer(), assets).bind()
    audio = AudioEngine(assets, backend=FakeAudioBackend()).enable_live_reload()
    hub = LiveDevelopmentHub(assets, renderer_bridge=bridge, audio=audio)

    assert hub.start() is hub
    assert hub.started
    assert hub.stop() is True
    assert hub.stop() is False
    assert bridge.bound
    assert audio.live_reload_enabled

    bridge.unbind()
    audio.disable_live_reload()


def test_hub_polls_plugin_and_shared_asset_pipeline_once(tmp_path):
    texture_path = tmp_path / "surface.png"
    texture_path.write_bytes(b"old")
    assets = AssetManager(tmp_path)
    assets.watch(texture_path)

    renderer = FakeRenderer()
    texture = FakeTexture()
    renderer._textures[str(texture_path.resolve())] = (texture, 2, 2)
    bridge = RendererAssetBridge(renderer, assets)

    plugin_result = ReloadResult("gameplay", tmp_path / "gameplay.py", True)
    plugins = FakePluginReloader(plugin_result)
    hub = LiveDevelopmentHub(assets, plugin_reloader=plugins, renderer_bridge=bridge)
    hub.start()

    texture_path.write_bytes(b"new-texture-data")
    result = hub.poll()

    assert plugins.polls == 1
    assert result.plugin_reloads == (plugin_result,)
    assert len(result.asset_reloads) == 1
    assert result.asset_reloads[0].kind == "modified"
    assert len(result.gpu_invalidations) == 1
    assert result.gpu_invalidations[0].released
    assert texture.released
    assert result.event_count == 3
    assert result.healthy
    assert hub.history == (result,)


def test_hub_routes_audio_and_gpu_invalidations_from_same_asset_change(tmp_path):
    sound_path = tmp_path / "theme.ogg"
    sound_path.write_bytes(b"old")
    assets = AssetManager(tmp_path)
    backend = FakeAudioBackend()
    audio = AudioEngine(assets, backend=backend)
    handle = audio.music("theme.ogg", loop=True)

    renderer = FakeRenderer()
    texture = FakeTexture()
    renderer._textures[str(sound_path.resolve())] = (texture, 1, 1)
    bridge = RendererAssetBridge(renderer, assets)
    hub = LiveDevelopmentHub(assets, renderer_bridge=bridge, audio=audio).start()

    original_token = handle._token
    sound_path.write_bytes(b"new-audio-data")
    result = hub.poll()

    assert len(result.asset_reloads) == 1
    assert len(result.gpu_invalidations) == 1
    assert len(result.audio_events) == 1
    assert result.audio_events[0].restarted == 1
    assert handle.active
    assert handle._token is not original_token
    assert backend.stops[-1] is original_token
    assert result.event_count == 3


def test_hub_history_skips_idle_polls_and_can_clear_subsystem_history(tmp_path):
    assets = AssetManager(tmp_path)
    bridge = RendererAssetBridge(FakeRenderer(), assets)
    audio = AudioEngine(assets, backend=FakeAudioBackend())
    hub = LiveDevelopmentHub(assets, renderer_bridge=bridge, audio=audio).start()

    result = hub.poll()
    assert not result.changed
    assert hub.history == ()

    bridge.invalidate_texture(tmp_path / "manual.png")
    audio._reload_events.append(
        __import__("swirengine").AudioReloadEvent(tmp_path / "manual.wav", 0, 0, 1)
    )
    hub.clear_history(clear_subsystems=True)

    assert bridge.invalidations == ()
    assert audio.reload_events == ()
