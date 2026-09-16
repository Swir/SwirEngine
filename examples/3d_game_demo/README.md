# SwirEngine 3D Game Demo

A short, asset-free first-person action example written as source code for SwirEngine. Its purpose is to show what a compact 3D game can look like when built directly on the engine APIs; it is not a separate game release.

The demo uses an original generated corridor/arena layout, primitive enemies, pickups, lighting, gameplay code and colors. It is inspired only by the broad classic corridor-FPS genre and does not copy maps, art, enemies, audio, names, weapons, or other assets from existing games.

## Run

From the repository root:

```bash
python examples/3d_game_demo/run_game.py
```

Controls:

- `W` / `A` / `S` / `D` — move
- Mouse or arrow keys — look
- Left mouse button or `Space` — fire
- Left/Right `Shift` — sprint
- `R` — restart

## What it demonstrates

- first-person camera movement and mouse look
- collision-constrained corridor movement
- hitscan-style shooting, ammo, enemy health and kill tracking
- simple line-of-sight enemy pursuit and attacks
- health/ammo pickups and a gated exit objective
- generated 3D meshes and primitive enemies with no external game assets
- Renderer 2.0, HDR/post-processing, shadows, SSAO, bloom and dynamic lights
- screen-space HUD/crosshair over a 3D scene
- deterministic headless gameplay validation plus real OpenGL smoke validation

The validation workflow also builds/runs the source against SwirEngine's actual OpenGL 3.3 renderer under Mesa/Xvfb, so the example is checked as executable engine code rather than documentation-only sample text.
