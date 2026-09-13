# Neon Snake 3D

A compact 3D Snake game built entirely with the public SwirEngine 1.x API.

## Gameplay

- **WASD** — steer the snake
- **R** — restart the round
- **ESC** — quit
- Eat the glowing red energy cube to grow and increase the score.
- Hitting the arena wall or your own body resets the round.
- The game keeps the session high score in memory.

## Visuals

The demo uses SwirEngine's real 3D renderer with PBR materials, emissive neon accents,
directional and point lights, shadows, ACES tone mapping, vignette and FXAA. No external
art assets are required.

## Run from source

```bash
python demo_projects/neon_snake_3d/run_game.py
```

From a fresh checkout install SwirEngine first:

```bash
python -m pip install -e .
python demo_projects/neon_snake_3d/run_game.py
```

## Standalone builds

The GitHub workflow builds one-file binaries for Windows, Linux and macOS. The Windows
binary is runtime-probed after packaging so a missing GLFW runtime causes CI to fail before
release publication.

If the Windows build cannot start on an end-user machine, the launcher writes
`NeonSnake3D-error.log` next to the executable and shows a diagnostic dialog.
