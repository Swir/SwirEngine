# SwirEngine examples

The small `demo_*.py` files focus on one subsystem at a time. The `sample_*.py` files are
larger, complete loops intended to show how several creator-facing APIs fit together.

## Official 3D validation game

`demo_projects/neon_cube_hunt_3d` is the full post-1.0 validation project. Unlike the focused
examples below, it is packaged as a standalone installable project and exercises the production
3D game path: PBR meshes, lights, shadows, post-processing, camera following, input, gameplay
state, CI smoke rendering, and cross-platform executable packaging.

Run it from the repository with:

```bash
python demo_projects/neon_cube_hunt_3d/run_game.py
```

The dedicated demo workflow also boots it under Xvfb/Mesa for multiple real OpenGL frames and
publishes source plus Windows/Linux/macOS one-file builds as a GitHub Release.

## Source game showcases and production fixtures

After the SwirEngine 1.4.0 engine release, repository-only game examples were added to make the
2D/3D/multiplayer authoring range obvious from source. They are **not separate products and do not
receive their own GitHub Releases**. The showcase-quality pass intentionally uses SwirEngine runtime
systems for core gameplay instead of reimplementing a mini engine inside each example. The 2D and
3D examples generate their own original visual/audio assets from source at runtime, so they remain
easy to inspect and redistribute without depending on a third-party game asset pack.

### SwirEngine 2D Game Demo

```bash
python examples/2d_game_demo/run_game.py
```

`2d_game_demo` is an original source-only scrolling platformer. The player is driven by
`PhysicsWorld2D` / `RigidBody2D` / `CollisionWorld2D`, while the game adds a multi-screen route,
checkpoint, stompable enemies, damage/respawn, collectible energy shards, a gated portal,
procedurally generated `Sprite2D` character/enemy/pickup art, parallax scenery, pooled VFX,
optional generated sound cues and a proper HUD. Its headless probe validates the same engine
physics stack used by the rendered demo.

### SwirEngine 3D Game Demo

```bash
python examples/3d_game_demo/run_game.py
```

`3d_game_demo` is an original source-only bunker FPS. Movement and collision use Physics 2.0 plus
`FirstPersonController3D`; weapon hits, AI obstacle avoidance and line-of-sight use engine sweeps.
The rendered example adds an authored bunker with runtime-generated textured `Material3D`
surfaces, composite robot enemies, chase/attack combat, health/ammo pickups, a multi-part
first-person weapon with muzzle light, optional generated sound cues, an extraction objective,
HUD/crosshair, Renderer 2.0, HDR tone mapping, SSAO, bloom and colored dynamic lighting.

Both rendered examples expose deterministic headless probes and are also booted through the real
OpenGL 3.3 renderer by the dedicated game-demo validation workflow.

### SwirEngine Multiplayer Game Demo

```bash
python examples/multiplayer_game_demo/run_game.py
```

`multiplayer_game_demo` is the deterministic source-only networking fixture. It drives four clients
and 32 replicated entities through the established replication, prediction/reconciliation, session,
transport/QoS and network-profiler path while injecting seeded packet loss, duplication, reordering,
latency and jitter. It is intentionally headless and offline so the same hostile-network workload can
be reproduced in CI without public sockets or an external service.

The SwirEngine 1.9 real-game production gate copies these exact 2D, 3D and multiplayer sources into
temporary projects, validates scene/content declarations, stages them with `ProjectExporter` and
runs the staged entrypoints. This makes the examples integration fixtures for creator workflows and
shipping regressions rather than disconnected demonstrations.

## Asset-free sample games

These two samples require no image or audio assets, so they are useful immediately after a
development install:

```bash
python examples/sample_breakout.py
python examples/sample_dodge_arena.py
```

### Breakout

`sample_breakout.py` combines scene objects, tags, screen-space UI, keyboard input, a game
update callback, simple collision logic, score/level progression, and scene cleanup/rebuilds.
It also demonstrates `Scene.remove_tagged(...)` for replacing a tagged group safely.

### Dodge Arena

`sample_dodge_arena.py` combines deterministic procedural spawning, keyboard movement,
screen-space HUD text, collision checks, difficulty progression, lives, round resets, and
bulk cleanup. It demonstrates both `Scene.remove_tagged(...)` and `Scene.remove_many(...)`.

## Creator-facing scene helpers

The scene API supports a few convenience operations that remain additive to the existing
`find`, `tagged`, `add`, and `remove` methods:

```python
player = game.scene.require("player")
enemies = game.scene.tagged("enemy")
removed = game.scene.remove_many(*enemies)
game.scene.remove_tagged("particle")
```

`Scene.require(name)` is useful when a named object is mandatory and raises `LookupError`
with the missing name. Bulk removal uses object identity and returns a stable tuple of the
objects that were actually removed.

For objects managed by `Game` subsystems such as registered physics or UI resources, prefer
`game.remove(obj)` for individual removal so subsystem cleanup hooks can run.
