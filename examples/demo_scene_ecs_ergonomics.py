from dataclasses import dataclass

from swirengine import ECSWorld, Prefab, Scene


@dataclass
class Position:
    x: float


@dataclass
class Velocity:
    x: float


class EnemyVisual:
    def __init__(self, name: str, hp: int = 100):
        self.name = name
        self.hp = hp

    def on_added_to_scene(self, _scene):
        print("added", self.name)

    def on_start(self, _scene):
        print("started", self.name)

    def update(self, _dt):
        pass

    def on_stop(self, _scene):
        print("stopped", self.name)


scene = Scene()
for index in range(1000):
    scene.compose_entity(Position(float(index)), name=f"prop-{index}")
runner = scene.compose_entity(Position(0.0), Velocity(4.0), name="runner")
scene.ecs.diagnostics.reset()
print("moving:", [entity.name for entity in scene.query_entities(Position, Velocity)])
print("query candidates:", scene.ecs.diagnostics.query_candidates)

prefab = Prefab(EnemyVisual("enemy"), name="enemy")
wave = prefab.instantiate_many(
    3,
    scene,
    overrides=(
        {"enemy": {"hp": 80}},
        {"enemy": {"hp": 100}},
        {"enemy": {"hp": 140}},
    ),
)
mount = scene.mount(*(instance.root for instance in wave), entities=(runner,))
scene.update(1 / 60)
print("snapshot rebuilds:", scene.diagnostics.snapshot_rebuilds)
print("wave hp:", [instance.root.hp for instance in wave])
print("unmounted:", mount.unmount())
