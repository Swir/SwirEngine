"""Unified live-development polling example.

This example shows the editor-style control flow. A real game/editor can also attach a
PluginAutoReloader and RendererAssetBridge; the hub keeps asset polling single-pass so every
subscriber sees the same invalidation transaction.
"""

from time import sleep

from swirengine import AssetManager, AudioEngine, LiveDevelopmentHub

assets = AssetManager("assets")
audio = AudioEngine(assets)
hub = LiveDevelopmentHub(assets, audio=audio).start()

print("Live development hub started. Press Ctrl+C to stop.")

try:
    while True:
        result = hub.poll()
        if result.changed:
            print(
                f"events={result.event_count} healthy={result.healthy} "
                f"assets={len(result.asset_reloads)} audio={len(result.audio_events)}"
            )
            for error in result.errors:
                print("error:", error)
        sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    hub.stop()
    audio.shutdown()
