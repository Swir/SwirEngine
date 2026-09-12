from dataclasses import dataclass

from swirengine import Scene, SceneInspector


@dataclass
class Actor:
    name: str
    enabled: bool = True
    health: int = 100


scene = Scene()
player = scene.add(Actor("Player"))
enemy = scene.create_entity(name="Enemy", tags={"hostile"})

inspector = SceneInspector(scene)
for row in inspector.hierarchy():
    print(row.kind, row.label, row.key)

inspector.select(player)
print(inspector.inspect())

inspector.set_property("health", 75)
print("health after edit:", player.health)
inspector.undo()
print("health after undo:", player.health)
inspector.redo()
print("health after redo:", player.health)

inspector.select(enemy)
print(inspector.inspect())
