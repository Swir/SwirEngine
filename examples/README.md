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

## Post-1.4 source game showcases

After the SwirEngine 1.4.0 engine release, two larger examples were added specifically to make the
2D/3D game-authoring range obvious from readable source code. These are repository examples only:
they are **not separate game products and do not receive their own GitHub Releases**.

### SwirEngine 2D Game Demo

```bash
python examples/2d_game_demo/run_game.py
```

`2d_game_demo` is an original, asset-free classic-platformer showcase with movement, jumping,
gravity, platform/gap collision, patrolling enemies, health, collectibles, a gated exit objective,
HUD state, restart flow and deterministic validation. It uses generated rectangles/colors rather
than third-party art or audio.

### SwirEngine 3D Game Demo

```bash
python examples/3d_game_demo/run_game.py
```

`3d_game_demo` is an original, asset-free classic corridor-FPS showcase with first-person camera
movement, mouse/keyboard look, sprinting, wall-constrained movement, hitscan-style combat, enemy
pursuit/attacks, health/ammo pickups, a gated exit, HUD/crosshair, Renderer 2.0, HDR post-processing,
shadows, SSAO, bloom and dynamic lights. Its layout and generated visuals are original rather than
copied from an existing game.

Both examples expose deterministic headless probes and are also booted through the real OpenGL 3.3
renderer by the dedicated game-demo validation workflow.

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
