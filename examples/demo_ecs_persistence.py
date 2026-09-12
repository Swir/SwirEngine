from dataclasses import dataclass

from swirengine import Scene, SceneCodecRegistry, SceneSerializer


@dataclass(slots=True)
class Position:
    x: float
    y: float


registry = SceneCodecRegistry.default()
registry.register(Position, name="demo.Position")
serializer = SceneSerializer(registry)

scene = Scene()
player = scene.create_entity(name="player", tags={"persistent"})
player.add(Position(12.0, 8.0))

serializer.dump_scene(scene, "save/player_scene.swirscene")
restored = serializer.load_scene("save/player_scene.swirscene")

loaded_player = restored.entities[0]
print(loaded_player.id, loaded_player.name, loaded_player.require(Position))
