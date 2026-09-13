# Neon Cube Hunt 3D

**Official SwirEngine 1.0 validation game**

Neon Cube Hunt 3D is a small, asset-free 3D game built only with the public SwirEngine 1.x API.
It is intentionally kept inside the main repository so every engine release can prove that a real
game can be assembled, simulated, rendered, packaged, and released with the documented API.

## What it exercises

- real `Game(..., mode="3d")` startup and OpenGL rendering
- `Mesh3D` + reusable `cube_mesh()` geometry
- PBR `Material3D` materials
- directional and point lights
- directional GPU shadows
- ACES/FXAA post-processing
- `Camera3D` follow/look-at behavior
- keyboard input and update callbacks
- scene names/tags and multiple gameplay objects
- deterministic gameplay logic that can be tested without a window
- PyInstaller packaging on Windows, Linux, and macOS

## Goal

Collect all six gold energy cores while avoiding the moving red hazard cubes. Finishing a set
starts a new round and increments the internal win counter. Losing all three lives resets the round.

## Controls

| Key | Action |
| --- | --- |
| `W A S D` | Move |
| `SPACE` | Boost |
| `R` | Reset round |
| `ESC` | Quit |

## Run from this repository

```bash
python -m pip install -e .
python demo_projects/neon_cube_hunt_3d/run_game.py
```

## Run as a standalone project

From this folder:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install .
neon-cube-hunt-3d
```

## Automated real-render smoke test

The repository workflow runs the game under Xvfb/Mesa on Linux with
`SWIR_DEMO_SMOKE_FRAMES=12`. The normal SwirEngine window/OpenGL path is used; after twelve rendered
frames the game stops itself. This complements unit tests that exercise movement, collection,
hazard damage, reset behavior, and the complete scene construction without requiring a display.

## Releases

The `Demo Game 3D Validation & Release` GitHub Actions workflow produces:

- a source-project ZIP,
- a Windows one-file executable,
- a Linux one-file executable,
- a macOS one-file executable,

and publishes them under the `demo-neon-cube-hunt-3d-v1.0.0` GitHub Release after the validated demo
lands on `main`.
