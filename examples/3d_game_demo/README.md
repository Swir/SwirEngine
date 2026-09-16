# SwirEngine 3D Game Demo

A source-only mini FPS showcase built to demonstrate a real SwirEngine game loop instead of a set of moving cubes. The bunker layout, enemy design, weapon, lighting and gameplay are original and are constructed entirely from SwirEngine primitives, so the example does not ship third-party game assets or a separate game release.

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
- an authored bunker with rooms, cover, trims, pylons, floor lanes and an objective door
- composite animated robot enemies instead of single debug cubes
- patrol, chase, attack, damage and kill states
- a multi-part first-person weapon with muzzle flash and dynamic light feedback
- health/ammo pickups, HUD, crosshair and gated extraction
- Renderer 2.0, HDR tone mapping, SSAO, bloom and colored dynamic lighting
- deterministic headless validation of the actual controller + physics weapon path
- real OpenGL 3.3 smoke boot in CI

The demo is inspired only by the broad classic first-person shooter genre. It does not copy maps, characters, art, audio, code, names, or other protected content from an existing game.
