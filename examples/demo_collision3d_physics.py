"""SwirEngine 1.3 3D collision/physics foundation demo.

This example intentionally runs without a window so the gameplay contract is easy to inspect and
can be reused in CI. The renderer remains independent: the same Cube3D objects can be added to a
normal 3D Game scene.
"""

from swirengine import (
    AABB3D,
    BoxCollider3D,
    CollisionWorld3D,
    Cube3D,
    PhysicsWorld3D,
    RigidBody3D,
    SphereCollider3D,
    Vec3,
)


def main() -> None:
    collisions = CollisionWorld3D(cell_size=2.0)

    player = Cube3D(position=Vec3(0.0, 2.0, 0.0), size=1.0, name="Player")
    floor = Cube3D(position=Vec3(0.0, -0.75, 0.0), size=8.0, name="Floor")
    pickup = Cube3D(position=Vec3(2.0, 1.0, 0.0), size=0.5, name="Pickup")

    player_collider = BoxCollider3D(player, tag="player", layer=1, mask=2)
    floor_collider = BoxCollider3D(
        floor,
        width=8.0,
        height=0.5,
        depth=8.0,
        tag="world",
        layer=2,
        mask=1,
    )
    pickup_collider = SphereCollider3D(pickup, radius=0.5, tag="pickup", layer=4)

    collisions.add(floor_collider)
    collisions.add(pickup_collider)

    physics = PhysicsWorld3D(
        collisions,
        gravity=Vec3(0.0, -9.81, 0.0),
        fixed_dt=1.0 / 60.0,
        max_substeps=8,
    )
    body = physics.add(
        RigidBody3D(
            player,
            player_collider,
            mass=1.0,
            linear_damping=0.05,
            restitution=0.0,
        )
    )

    body.apply_impulse(1.0, 0.0, 0.0)
    for _ in range(120):
        physics.step(1.0 / 60.0)

    nearby = collisions.overlap_sphere(player.position, 3.0)
    ray_hits = collisions.raycast(Vec3(-4.0, 1.0, 0.0), Vec3(1.0, 0.0, 0.0), max_distance=10.0)
    world_hits = collisions.overlap_box(AABB3D(0.0, -0.75, 0.0, 10.0, 1.0, 10.0))

    print("player position:", player.position)
    print("nearby tags:", tuple(collider.tag for collider in nearby))
    print("ray hits:", tuple((hit.collider.tag, round(hit.distance, 3)) for hit in ray_hits))
    print("world overlap:", tuple(collider.tag for collider in world_hits))
    print("collision diagnostics:", collisions.diagnostics)
    print("physics dropped time:", physics.dropped_time)


if __name__ == "__main__":
    main()
