from dataclasses import dataclass

from swirengine import Scene, SceneCodecRegistry, SceneSerializer


@dataclass(slots=True)
class Position:
    x: float
    y: float


@dataclass(slots=True)
class Relationship:
    owner: object
    target: object


registry = SceneCodecRegistry.default()
registry.register(Position, name="demo.Position")
registry.register(Relationship, name="demo.Relationship")
serializer = SceneSerializer(registry)

scene = Scene()
player = scene.create_entity(name="player", tags={"persistent"})
enemy = scene.create_entity(name="enemy", tags={"persistent"})
player_position = player.add(Position(12.0, 8.0))
enemy.add(Position(20.0, 8.0))
player.add(Relationship(player, enemy.require(Position)))
enemy.add(Relationship(enemy, player_position))

serializer.dump_scene(scene, "save/player_scene.swirscene")
restored = serializer.load_scene("save/player_scene.swirscene")

loaded_player = restored.ecs.find("player")
loaded_enemy = restored.ecs.find("enemy")
assert loaded_player is not None
assert loaded_enemy is not None
print(loaded_player.require(Relationship).owner is loaded_player)
print(loaded_player.require(Relationship).target is loaded_enemy.require(Position))
