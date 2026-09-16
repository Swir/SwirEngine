# SwirEngine 1.4 — Integrated Production Showcase

The final SwirEngine 1.4 milestone requires one deterministic integration target that proves the
major 1.4 systems can coexist in a single creator-facing scenario instead of being validated only by
isolated milestone tests.

`demo_projects/showcase_1_4/run_game.py` is that target. It is intentionally self-contained and uses
only generated terrain plus built-in engine primitives, so CI and release candidates do not depend on
external assets or network services.

## Systems exercised together

The showcase builds one 3D `Game` and drives the following 1.4 surfaces in one execution:

- **Terrain + World LOD** — procedural heightmap generation, chunk LOD selection, terrain collision
  raycast, and `LargeWorldStreamer` activation into the live game scene.
- **Physics 2.0 + Character Controllers** — a deterministic collision course using `PhysicsScene3D`
  and `CharacterController3D`, including step/sweep work and a forward traversal assertion.
- **Renderer 2.0** — the game is configured for cascaded shadows, SSAO, HDR, bloom, decals and ACES
  post-processing through the additive Renderer2 configuration surface.
- **GPU VFX** — one 4,096-slot GPU particle emitter queues a deterministic burst and continuous
  emissions; release validation can additionally execute the real Renderer2/VFX path under Mesa/Xvfb.
- **Editor Authoring Power** — the same live scene is inspected through `EditorAuthoringSession`, a
  scene object is selected, and a grouped gizmo translation is verified.
- **Multiplayer 2.0** — the character result is replicated into canonical snapshots, encoded as a
  sparse delta, interpolated, packetized and counted by the bandwidth diagnostics.

The existing final readiness matrix still runs the dedicated real OpenGL 3.3 Renderer2, GPU-particle
and Hi-Z smokes, the individual performance contracts and the full regression suite. The showcase is
an integration contract; it does not replace subsystem-specific depth testing.

## Headless validation

Run:

```bash
python demo_projects/showcase_1_4/run_game.py
```

The default mode does not open a window. It performs deterministic simulation/integration work and
prints one compact result line only after every assertion succeeds. This mode is suitable for normal
CI and clean-wheel validation.

## Real Renderer2/VFX smoke

On a machine with an OpenGL 3.3 display, or in CI under Xvfb/Mesa:

```bash
SWIR_1_4_SHOWCASE_RENDER=1 SWIR_1_4_SHOWCASE_FRAMES=12 \
  xvfb-run -a python demo_projects/showcase_1_4/run_game.py
```

The showcase then boots the real `Game.run()` path using Renderer2 and the GPU VFX scene and exits
automatically after the requested validation-frame budget. `SWIR_1_4_SHOWCASE_FRAMES` is bounded by
the caller and defaults to 12.

## Release meaning

A passing showcase demonstrates cross-system compatibility only. SwirEngine 1.4 must still satisfy
all release-readiness checks: the complete regression matrix, deterministic performance contracts,
real OpenGL smokes, wheel/sdist metadata checks, clean-wheel imports, Windows CPython 3.14 packaging,
roadmap/version synchronization and the guarded publication workflow.
