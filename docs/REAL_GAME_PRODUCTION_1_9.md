# SwirEngine 1.9 Real-Game Production Gate

SwirEngine 1.9 treats representative games as integration fixtures, not release artifacts. The gate
exists to prove that creator-facing systems can survive a realistic source-to-staged workflow instead
of passing only isolated subsystem tests.

## Representative fixtures

The gate uses the repository's maintained source games directly:

- `examples/2d_game_demo` — physics-driven scrolling platformer with HUD, enemies, checkpoints,
  collectibles, generated art/audio and a deterministic headless gameplay probe.
- `examples/3d_game_demo` — Renderer 2.0 bunker FPS with first-person controller, Physics 2.0,
  collision sweeps, combat, AI, materials, lighting, HUD and a deterministic headless probe.
- `examples/multiplayer_game_demo` — deterministic replication/prediction fixture with seeded packet
  loss, duplication, reordering, latency and jitter.

These directories remain source-only examples. They do not receive independent GitHub Releases.

## What the production verifier proves

`tools/verify_real_game_production_1_9.py` copies each representative source into an isolated project
and creates production metadata around that exact game code. For every fixture it then:

1. creates deterministic title/gameplay scene documents with `SceneSerializer`;
2. creates and reloads shipping-safe project input and settings defaults, including the required
   semantic UI actions;
3. persists and reloads a player input override plus accessibility settings inside the profile tree;
4. performs a real background manual-save write and recovery read through `ProductionGameStateSession`;
5. loads and validates the `[scenes]` registry, including the dependency transition path;
6. loads and validates a `[content.build]` graph with preload/stream classifications;
7. derives a deterministic `ProjectExporter` plan twice and rejects plan drift;
8. stages the project for the current host desktop target;
9. requires the entrypoint, manifest, project controls/settings, declared assets and declared scenes to
   be present in the staged output even when they were not all listed directly in the packaging profile;
10. requires deterministic SHA-256 entries for the required shipping files and verifies that per-player
    user data is not copied into project shipping content;
11. in runtime mode, launches both the copied source entrypoint and the staged entrypoint and requires
    successful completion.

The user-data round trip is deliberately outside the staged project tree: project defaults ship with
the game, while player overrides/settings/saves remain profile data. This prevents the production gate
from accidentally treating private player state as redistributable content.

The verifier deliberately does not invoke PyInstaller. Native desktop executable creation is owned by
the separate SwirEngine 1.9 desktop-shipping gate, which already validates clean-wheel native builds
on Windows, Linux and macOS. Keeping the two gates separate makes failures attributable while still
covering the complete path across the 1.9 validation matrix.

## Run locally

After a development install:

```bash
python tools/verify_real_game_production_1_9.py
```

For a fast packaging/content/state check without launching game entrypoints:

```bash
python tools/verify_real_game_production_1_9.py --staging-only
```

The command prints JSON containing one report per fixture plus an aggregate fingerprint. A successful
report has `status: "ok"`. Each fixture records scene/content/input/settings/game-state fingerprints and
the staged export-manifest hash. Runtime fields are `true` only when both source and staged entrypoints
were actually executed; staging-only mode leaves those fields unset rather than claiming runtime coverage.

## CI contract

`.github/workflows/real-game-production-1-9.yml` runs the focused production regression suite and the
full source-to-staged verifier on supported Python contract versions. It also runs staging validation
on Windows, Linux and macOS. Existing workflows continue to own real OpenGL demo boots, multiplayer
soak/transport validation, and native desktop executable creation.

Milestone progress must not be raised merely because this file or the workflow exists. Milestone 9 is
complete only after the exact implementation head passes its required gates and the roadmap closeout
head is re-verified. The next public GitHub Release and PyPI publication remain SwirEngine 2.0.
