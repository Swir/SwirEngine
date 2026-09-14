# Scene / Prefab / ECS ergonomics — SwirEngine 1.2

SwirEngine 1.2 keeps the existing `Scene`, `Prefab`, `Entity` and `ECSWorld` APIs compatible while reducing repeated Python work in larger worlds and making room/chunk composition easier.

## Scene lifecycle

Ordinary scene objects may optionally expose these hooks:

- `on_added_to_scene(scene)` — called once when the object is first registered,
- `on_start(scene)` — called before its first enabled update after registration,
- `on_stop(scene)` — called when a started object is removed,
- `on_removed_from_scene(scene)` — called whenever a registered object is removed.

Objects that do not implement the hooks behave exactly as before. `Scene.update()` uses a cached stable object snapshot, so an unchanged scene no longer creates a fresh tuple for traversal every frame. `scene.diagnostics.snapshot_rebuilds` and `object_updates` make that work observable without claiming an unmeasured FPS increase.

## Grouped world composition

`Scene.mount()` groups scene objects and already-owned ECS entities into a lightweight `SceneMount`:

```python
room_enemy = scene.compose_entity(Health(100), Position(12, 8), tags={"enemy"})
with scene.mount(room_mesh, room_trigger, entities=(room_enemy,)):
    run_room()
# room-owned objects/entities are removed here
```

`SceneMount.unmount()` is idempotent and returns `(removed_objects, removed_entities)`. This is useful for rooms, encounters, procedural chunks and streamed regions.

`Scene.compose_entity()` / `ECSWorld.compose_entity()` create an entity and attach a component bundle in one call. If the bundle fails (for example duplicate concrete component types), the newly created entity is rolled back instead of leaving a partial entity in the world.

## Indexed ECS queries

Component membership is indexed as components are added and removed. A query uses compatible component indexes to build the smallest practical candidate set, then preserves deterministic entity insertion order and the existing subclass-aware semantics.

For example, with 1000 `Position`-only entities and one `Position + Velocity` entity, `query(Position, Velocity)` visits a single indexed candidate rather than performing component lookup across all 1001 entities.

`ECSDiagnostics` exposes:

- `query_calls`,
- `query_candidates`,
- `query_matches`,
- `system_updates`.

These counters are deterministic regression instrumentation, not an end-to-end FPS claim.

## System lifecycle and scheduling

ECS systems may optionally expose `on_added_to_world(world)` and `on_removed_from_world(world)`. Priority/order sorting is cached until system registration changes, avoiding repeated sort/tuple work on stable worlds.

## Prefab batches

`Prefab.instantiate_many(count, scene, overrides=...)` creates independent deep-copied object graphs in deterministic spawn order. A per-instance override sequence is optional and must match `count`.

This is intended for waves, repeated props and chunk population while preserving the established prefab graph-isolation contract.
