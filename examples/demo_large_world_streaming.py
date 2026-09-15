from __future__ import annotations

from swirengine.core.scene import Scene
from swirengine.graphics.primitives import Rectangle2D
from swirengine.large_world import (
    ChunkContent,
    ChunkDefinition,
    ChunkKey,
    LargeWorldSettings,
    LargeWorldStreamer,
)


def make_chunk(key: ChunkKey) -> ChunkDefinition:
    def build(context):
        marker = Rectangle2D(
            context.center.x,
            context.center.y,
            context.chunk_size * 0.8,
            context.chunk_size * 0.8,
            name=f"chunk-{key.x}-{key.y}",
        )
        return ChunkContent(objects=(marker,))

    return ChunkDefinition(key, build, name=f"sector-{key.x}-{key.y}")


def main() -> None:
    scene = Scene()
    streamer = LargeWorldStreamer(
        scene,
        make_chunk,
        settings=LargeWorldSettings(
            chunk_size=32,
            dimensions=2,
            active_radius_chunks=1,
            preload_radius_chunks=2,
            retention_radius_chunks=3,
            max_activations_per_update=3,
            max_deactivations_per_update=16,
        ),
    )

    for focus_x in (0.0, 16.0, 40.0, 96.0, 192.0):
        result = streamer.update((focus_x, 0.0))
        print(
            f"focus={result.focus_key} "
            f"active={len(streamer.active_keys)} "
            f"tracked={result.diagnostics.tracked_chunks} "
            f"activated={result.activated} "
            f"deactivated={result.deactivated}"
        )

    print(f"scene_objects={len(scene.objects)}")
    print(f"active_chunks={streamer.active_keys}")
    streamer.unload_all()
    print(f"after_unload_scene_objects={len(scene.objects)}")


if __name__ == "__main__":
    main()
