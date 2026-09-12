from dataclasses import dataclass

from swirengine import Scene


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    x: float
    y: float


scene = Scene()
player = scene.create_entity(name="player", tags={"controllable"})
player.add(Position(0.0, 0.0))
player.add(Velocity(3.0, 1.5))


def movement_system(world, dt):
    for _entity, position, velocity in world.rows(Position, Velocity):
        position.x += velocity.x * dt
        position.y += velocity.y * dt


scene.ecs.add_system(movement_system)
scene.update(1.0 / 60.0)

position = player.require(Position)
print(f"player: ({position.x:.3f}, {position.y:.3f})")
