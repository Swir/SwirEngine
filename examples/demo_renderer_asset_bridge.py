"""Minimal live GPU texture invalidation wiring for an editor/game loop."""

from swirengine import AssetManager, RendererAssetBridge


def attach_live_textures(renderer, scene):
    assets = AssetManager("assets")
    bridge = RendererAssetBridge(renderer, assets).bind()
    bridge.watch_scene_textures(scene)
    return bridge


def update_live_textures(bridge, scene):
    for result in bridge.poll(scene_or_objects=scene):
        if result.error:
            print(f"asset reload failed: {result.path}: {result.error}")
        elif result.kind != "deleted":
            print(f"asset changed: {result.path}")
