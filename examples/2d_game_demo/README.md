# SwirEngine 2D Game Demo

A source-only scrolling platformer showcase built to look and behave like a small game, not a renderer probe. Core movement and collision use SwirEngine physics. Instead of shipping an external art pack, `procedural_art.py` creates original player/enemy animation frames, energy shards, the portal, and short sound cues at runtime; the rendered game then uses those assets through SwirEngine `Sprite2D` and audio APIs.

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
- runtime-generated original `Sprite2D` player/enemy/pickup art with movement animation and facing
- patrol enemies, stomp combat, damage, respawn and game-over flow
- energy-shard collection and a gated portal objective
- smooth camera follow with star / mountain / skyline parallax
- pooled particle feedback for jumps, pickups, checkpoint and combat
- optional generated sound cues through `Game.sound` when the audio extra is installed
- HUD/objective UI
- deterministic headless validation of the real engine physics stack
- real OpenGL 3.3 smoke boot in CI

The generated artwork and audio are original to this example. The demo is inspired only by the broad side-scrolling platformer genre and does not copy characters, art, level layouts, audio, names, or other protected content from existing games.
