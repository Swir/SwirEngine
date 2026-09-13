from swirengine import AABB, BoxCollider2D, CollisionWorld2D, Rectangle2D


world = CollisionWorld2D(cell_size=64)
player = world.add(BoxCollider2D(Rectangle2D(0, 0, 32, 32), tag="player", layer=1))
for index in range(40):
    world.add(
        BoxCollider2D(
            Rectangle2D(80 + index * 48, 0, 24, 24),
            tag="enemy",
            layer=2,
        )
    )

nearby = world.overlap_aabb(AABB(240, 0, 320, 120), layer_mask=2)
ray_hits = world.raycast(0, 0, 1, 0, max_distance=1000, layer_mask=2)

print(f"nearby enemies: {len(nearby)}")
print(f"ray hits: {len(ray_hits)}")
if ray_hits:
    first = ray_hits[0]
    print(f"first hit distance: {first.distance:.1f}")

world.query(player)
print(f"broad-phase diagnostics: {world.diagnostics}")
