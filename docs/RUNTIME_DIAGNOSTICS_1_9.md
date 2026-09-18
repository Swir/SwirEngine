# Runtime Diagnostics, Crash Reports & Support Bundles — SwirEngine 1.9

SwirEngine 1.9 adds an **opt-in** support path for a shipped game. The contract is deliberately
privacy-conservative: creating a diagnostic object does not inspect the user's environment, command
line, home directory contents, browser data, save files or arbitrary project/user files.

## Goals

- give a creator enough structured information to reproduce a crash;
- keep logs, tracebacks and snapshots bounded for long-running games;
- preserve stable 1.x runtime APIs by making the system additive;
- let a player intentionally export a small support bundle that contains generated diagnostics only;
- reject corrupt, oversized or non-portable report data before it reaches tooling.

## Privacy contract

`capture_exception()` records only data that the game explicitly supplies plus the exception type,
bounded exception message and traceback frame identity. It does **not** capture Python locals or source
lines. External traceback paths are reduced to basenames. Project-contained traceback files become
project-relative paths. Project/home path strings and common inline credential patterns in exception
messages are scrubbed, and structured fields whose names resemble passwords, tokens, cookies,
authorization headers, credentials, session IDs or API keys are replaced with `<redacted>`.

The support ZIP has exactly two generated entries:

- `bundle.json` — schema, hashes and explicit privacy flags;
- `report.json` — the validated portable crash report.

There is intentionally no `add_file()` API. Saves, screenshots, configuration files and user documents
must never be swept into a support package implicitly.

## Creator flow

```python
from swirengine.diagnostics19 import (
    RuntimeLogBuffer,
    capture_exception,
    create_support_bundle,
    identity_from_project,
)
from swirengine.project19 import ProjectManifest

project = ProjectManifest.load(".")
identity = identity_from_project(
    project,
    engine_version="1.9-source",
    build_id="build-2026-09-18",
    profile="windows",
)
logs = RuntimeLogBuffer(capacity=128)
logs.record("info", "entered arena", scene="arena")

try:
    run_gameplay()
except Exception as exc:
    report = capture_exception(
        exc,
        identity=identity,
        logs=logs,
        diagnostics={"scene": "arena", "players": 1},
        project_root=project.root,
    )
    report.export_json("support/crash-report.json")
    create_support_bundle(report, "support/support.zip")
```

Applications should still ask the player before sharing the resulting ZIP. SwirEngine only creates the
local artifact; it does not upload or transmit it.

## Existing performance diagnostics

`capture_exception(..., performance=diagnostics)` accepts the existing `PerformanceDiagnostics2`
recorder. Its bounded capture is converted into the same portable, size-limited snapshot. This keeps
runtime support integrated with the established 1.5 diagnostics subsystem instead of introducing a
second profiler.

## Bounds and hardening

- report JSON: at most 512 KiB;
- log history: at most 256 entries;
- log message / exception message: at most 2,048 characters;
- structured mapping: at most 64 fields per level and four mapping levels;
- sequence values: at most 64 items;
- traceback: at most 64 frames;
- non-finite floating-point values are rejected;
- support output must be a `.zip` and receives fixed entry timestamps and sorted names;
- JSON loading validates schema/version before reconstructing typed report objects.

The dedicated 1.9 validation workflow exercises Python 3.10, 3.13 and 3.14, corruption/size failure
cases, privacy redaction, support-bundle inventory, the creator demo, Ruff/compile and a bounded
synthetic report workload. These timings are regression contracts, not FPS/runtime performance claims.

## Scope

This source-only API is part of the SwirEngine 1.9 production-workflow roadmap. It does not change the
published 1.5.0 package or release policy. `Release/PyPI: frozen until SwirEngine 2.0`.
