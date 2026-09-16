# SwirEngine 2D Game Demo

A small, asset-free platformer written as a source-code showcase for SwirEngine. It demonstrates the kind of classic 2D game loop that can be built with the engine without shipping a separate game product or release.

The level, colors, characters, collectibles, and gameplay are original generated primitives. The example is inspired only by the broad classic platformer genre and does not copy art, level data, characters, audio, names, or other assets from existing games.

## Run

From the repository root:

```bash
python examples/2d_game_demo/run_game.py
```

Controls:

- `A` / `D` or Left / Right — move
- `Space` — jump
- `R` — restart

## What it demonstrates

- a complete update-driven 2D game loop
- keyboard input and jump/platform movement
- deterministic gravity and platform collision resolution
- gaps, elevated platforms, patrolling enemies and player damage
- collectibles and a gated level objective
- health, collectible progress and status HUD
- scene primitives with no external image/audio dependencies
- deterministic headless validation for CI

The game-demo validation workflow also boots this example through the real OpenGL renderer under Mesa/Xvfb.
