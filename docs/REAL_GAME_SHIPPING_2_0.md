# SwirEngine 2.0 — Representative Real-Game Shipping Gate

This document defines the candidate contract for SwirEngine 2.0 Milestone 6. It does not mark the milestone complete by itself; the exact implementation head and the later roadmap closeout head must pass the required CI/regression matrix.

## Scope

The gate treats the maintained source-only 2D, 3D and multiplayer projects as engine integration fixtures rather than decorative demos. Each fixture is copied into an isolated project, given production scene/content/input/settings/save configuration, validated, staged with `ProjectExporter`, exercised through the bounded runtime-diagnostics contract and—when runtime validation is enabled—executed both from source and from the staged output.

The three required fixtures are:

- `examples/2d_game_demo/`
- `examples/3d_game_demo/`
- `examples/multiplayer_game_demo/`

## Production workflow contract

The 2.0 gate builds on the already verified 1.9 real-game production path and requires all three fixtures to preserve:

- deterministic project, scene, content, input/settings, game-state, runtime-diagnostics and export-manifest evidence;
- required scene and generated project configuration in the staged package;
- source and staged entrypoint execution when runtime validation is enabled;
- game/player configuration and saves in an external user-data root rather than redistributed project content;
- deterministic rejection of missing declared scenes and missing project entrypoints before a successful shipping result can be claimed.

The gate intentionally reuses the existing project manifest, scene package, content graph, shipping defaults, save/profile, diagnostics and export systems instead of creating a parallel demo-only shipping abstraction.

## Runtime diagnostics evidence

Each representative fixture receives a `RuntimeIdentity` derived from its real production `ProjectManifest`. The gate captures and JSON-roundtrips a bounded synthetic failure through the existing 1.9 diagnostics implementation and requires a deterministic SHA-256 report fingerprint.

The probe deliberately includes a secret-like field and the temporary project path, then verifies that neither raw value survives the privacy scrub. This keeps diagnostics tied to the representative game workflow while preserving the established rule that reports do not automatically collect the process environment, argv or arbitrary user files.

The diagnostics evidence is verification-only. It is not shipped as project content and does not create player save/profile data.

## Player-local data boundary

Player input overrides, display/accessibility settings, profiles and saves belong to the external user-data tree created by the production game-state session. They are not project source assets and are not allowed in the staged shipping inventory. The verifier rejects exported paths containing user-data/profile/save or input-override content.

Version-controlled defaults under `config/` remain project content because they are creator-authored shipping defaults, not player-local state.

## Failure paths

Milestone 6 must prove that representative projects fail safely when required shipping content is broken. The verifier currently locks two foundational cases:

1. a declared gameplay scene is removed after project preparation;
2. the project entrypoint is removed before export.

Both cases must fail deterministically before a successful package/runtime claim is produced. Additional failure-path coverage can be added when it exercises a real production risk rather than duplicating parser unit tests.

## Verification

Run the staging contract:

```bash
python tools/verify_real_game_shipping_2_0.py --staging-only
```

Run the full source + staged runtime contract:

```bash
python tools/verify_real_game_shipping_2_0.py
```

Run the focused regression:

```bash
python -m pytest -q tests/test_real_game_shipping_2_0.py
```

The dedicated `Real-Game Shipping 2.0` workflow runs the full contract on Python 3.10, 3.13 and 3.14. Full repository CI, locked historical compatibility/source checkpoints, multiplayer production, runtime scalability, platform support and desktop export/shipping gates remain required before Milestone 6 may move from 5/10 to 6/10.

## Release policy

The fixtures remain source-only integration assets and receive no separate releases. This milestone does not publish SwirEngine, change the public package version or authorize a beta.

`Release/PyPI: frozen until SwirEngine 2.0`
