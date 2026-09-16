# SwirEngine 2D Game Demo

A source-only platformer showcase built to look and behave like a small game, not a renderer probe. It ships no third-party art, music, or copied level data: the visual identity is constructed from layered SwirEngine primitives and pooled VFX so the whole example remains readable in the repository.

## Run

```bash
python examples/2d_game_demo/run_game.py
```

Controls:

- `A` / `D` or Left / Right — move
- `Space` — jump
- `R` — restart

## What it demonstrates

- `PhysicsWorld2D`, `RigidBody2D` and `CollisionWorld2D` driving the player
- a scrolling multi-screen level with gaps, elevated routes and a checkpoint
- layered player/enemy visuals assembled from engine primitives
- patrol enemies, stomp combat, damage, respawn and game-over flow
- energy-shard collection and a gated portal objective
- smooth camera follow with star / mountain / skyline parallax
- pooled particle feedback for jumps, pickups, checkpoint and combat
- HUD/objective UI
- deterministic headless validation of the real engine physics stack
- real OpenGL 3.3 smoke boot in CI

The demo is inspired only by the broad side-scrolling platformer genre. It does not copy characters, art, level layouts, audio, names, or other protected content from existing games.
