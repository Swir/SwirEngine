from __future__ import annotations

from swirengine import Cube3D, Vec3
from swirengine.navigation import NavigationAgent3D, NavigationGrid3D


def main() -> None:
    grid = NavigationGrid3D(12, 8, cell_size=1.0, origin=Vec3(0, 0, 0), diagonal=True)
    grid.set_blocked_many(tuple((5, z) for z in range(8) if z != 4))
    grid.set_cost((8, 4), 3.0)

    actor = Cube3D(position=Vec3(0.2, 0.0, 0.2), size=0.5, name="agent")
    agent = NavigationAgent3D(actor, grid, speed=3.0, stopping_distance=0.05)
    destination = Vec3(10.2, 0.0, 6.2)

    if not agent.set_destination(destination):
        raise RuntimeError("demo route could not be generated")

    assert agent.path is not None
    print("Initial cells:", agent.path.cells)
    print("Initial path cost:", round(agent.path.cost, 3))

    for step in range(240):
        if step == 60:
            # Dynamic obstacle update invalidates cached routes; the agent repaths automatically.
            grid.set_blocked((5, 4))
            grid.set_blocked((5, 2), False)
        agent.update(1.0 / 60.0)
        if not agent.has_path:
            break

    print(
        "Agent position:",
        round(actor.position.x, 3),
        round(actor.position.y, 3),
        round(actor.position.z, 3),
    )
    print("Grid revision:", grid.revision)
    print("Navigation diagnostics:", grid.diagnostics)


if __name__ == "__main__":
    main()
