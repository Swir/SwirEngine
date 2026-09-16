# SwirEngine 3D Game Demo

A source-only mini FPS showcase built to demonstrate a real SwirEngine game loop instead of a set of moving cubes. The bunker, enemies, weapon and lighting are original. `procedural_art.py` generates metal, floor, hazard and control-panel textures plus short sound cues at runtime, so the example can demonstrate textured `Material3D` surfaces and audio without shipping a third-party asset pack or a separate game release.

## Run

```bash
python examples/3d_game_demo/run_game.py
```

Controls:

- `W` / `A` / `S` / `D` — move
- Mouse or arrow keys — look
- Left mouse or `Space` — fire
- Left Shift — sprint
- `R` — restart

## What it demonstrates

- Physics 2.0 `PhysicsScene3D` world registration and collision sweeps
- production `FirstPersonController3D` movement, gravity, ground probing and wall handling
- Physics 2.0 sphere sweeps for weapon hits and AI obstacle / line-of-sight checks
- an authored bunker with rooms, cover, trims, pylons and an objective door
- runtime-generated original textures used through `Material3D` metallic/roughness materials
- composite animated robot enemies instead of single debug cubes
- patrol, chase, attack, damage and kill states
- a multi-part first-person weapon with muzzle flash and dynamic light feedback
- health/ammo pickups, HUD, crosshair and gated extraction
- optional generated shot/pickup/damage sound cues through `Game.sound`
- Renderer 2.0, HDR tone mapping, SSAO, bloom and colored dynamic lighting
- deterministic headless validation of the actual controller + physics weapon path
- real OpenGL 3.3 smoke boot in CI

The generated textures and audio are original to this example. The demo is inspired only by the broad classic first-person shooter genre and does not copy maps, characters, art, audio, code, names, or other protected content from an existing game.
