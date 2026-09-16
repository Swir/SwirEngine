from __future__ import annotations

from dataclasses import dataclass

from swirengine.core.scene import Scene
from swirengine.world_streaming_easy15 import WorldStream


@dataclass
class Landmark:
    name: str
    x: float
    y: float


def main() -> None:
    scene = Scene()
    world = WorldStream(
        scene,
        dimensions=2,
        chunk_size=100.0,
        radius=1,
        budget=9,
        loads_per_update=2,
        unloads_per_update=4,
        retention_updates=1,
    )

    @world.chunk("spawn-town", (0, 0), priority=10)
    def spawn_town(ctx):
        return Landmark("spawn-town", ctx.center.x, ctx.center.y)

    @world.chunk("east-road", (1, 0), dependencies=("spawn-town",))
    def east_road(ctx):
        return [
            Landmark("east-road", ctx.center.x, ctx.center.y),
            ctx.scene.create_entity(name="east-road-trigger"),
        ]

    @world.chunk("forest", (2, 0), cost=2)
    def forest(ctx):
        return (
            Landmark("forest-gate", ctx.origin.x + 20.0, ctx.center.y),
            Landmark("forest-camp", ctx.origin.x + 70.0, ctx.center.y),
        )

    print("SwirEngine 1.5 World Streaming 2.0 creator demo")
    for focus in ((20.0, 20.0), (120.0, 20.0), (220.0, 20.0), (320.0, 20.0)):
        result = world.warmup(focus)
        print(
            f"focus={focus} active={world.active} "
            f"loaded={result.activated} unloaded={result.deactivated} "
            f"scene_objects={len(scene)}"
        )

    print("active cost:", world.diagnostics.active_cost)
    print("runtime fingerprint:", world.state_fingerprint())
    print("unloaded:", world.unload_all())


if __name__ == "__main__":
    main()
