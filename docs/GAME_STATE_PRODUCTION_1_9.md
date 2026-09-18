# SwirEngine 1.9 — Save, Profile & Game-State Production Integration

This source-only 1.9 subsystem integrates the already verified Save/Profile 2.0 and background-save foundations into a bounded production workflow. It does not change the public 1.5.0 package and does not publish an intermediate release.

## Goals

`ProductionGameStateSession` gives a game one explicit owner for:

- deterministic per-project and per-profile user-data paths;
- manual save-slot budgets;
- rotating autosaves with interval gating and one autosave in flight at a time;
- immutable snapshot preflight before background I/O;
- a configurable maximum snapshot size;
- versioned save migrations and migration diagnostics;
- primary/backup integrity recovery through `SaveSlotStore2`;
- persisted 1.9 display/accessibility settings in the same profile tree;
- portable diagnostics suitable for support tooling and the later 1.9 diagnostics milestone.

The orchestrator composes existing verified components rather than replacing them: `ProfileSaveManager2`, `SaveSlotStore2`, `BackgroundSavePipeline`, `MigrationRegistry` and the 1.9 `SettingsStore`.

## User-data policy

`resolve_user_data_root(app_id)` uses only supported desktop policies:

| Platform | Default root |
|---|---|
| Windows | `%LOCALAPPDATA%\SwirEngine\<app_id>` with a home fallback |
| macOS | `~/Library/Application Support/SwirEngine/<app_id>` |
| Linux | `$XDG_DATA_HOME/swirengine/<app_id>` or `~/.local/share/swirengine/<app_id>` |

Relative environment overrides are ignored. Unsupported platforms fail explicitly. Tests and portable tools can supply an explicit root without pretending to validate another OS filesystem.

Treat the application id as persistent shipped identity. `project_app_id()` provides a readable default from a project name, while a production game should keep its chosen id stable across updates.

## Manual saves and autosaves

Manual slots are bounded by `SaveProductionPolicy.max_manual_slots`. Snapshot data must be portable JSON and is captured and sized before background work starts. The background pipeline then performs atomic primary/backup writes and reads the committed primary back before success is reported.

`submit_autosave()` applies the configured interval and uses a rotating generation ring. The orchestrator allows at most one autosave request in flight so periodic game-loop calls cannot build an unbounded queue. `force=True` bypasses the interval but never bypasses the single-flight safety rule.

`load_latest_autosave()` tries generations newest-first and uses the existing integrity/recovery contract. A corrupt primary can recover from its verified backup when one exists.

## Migrations, recovery and settings

Save versions use `MigrationRegistry`. Loading records `migrations_applied`, whether backup recovery was required, and the final result in `GameStateDiagnostics`. `upgrade=True` can write migrated data back through the safe save contract.

`session.settings_store()` returns the 1.9 shipping `SettingsStore` at `<user-data-root>/profiles/<profile>/config/game-settings.json`. This keeps per-user display/accessibility settings outside project content and beside the profile save tree without merging configuration into game-state blobs.

## Bounded defaults

The default policy is intentionally conservative: 3 autosave generations, a 120 second interval, 16 manual slots, a 4 MiB captured-snapshot ceiling, 16 background requests and 2 save workers. Projects may tune these within hard safety bounds. These are orchestration budgets, not performance guarantees.

## Verification

The dedicated source gate runs on Python 3.10, 3.13 and 3.14 and covers platform path policy, save roundtrips, autosave rotation, snapshot-size rejection before I/O, backup recovery, migration accounting, settings persistence, lifecycle shutdown, existing Save/Profile regressions, creator demo, Ruff, compile and a bounded I/O workload.

SwirEngine 1.9 remains source-only. `Release/PyPI: frozen until SwirEngine 2.0`.
