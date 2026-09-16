# Project System 2.0 — SwirEngine 1.5

SwirEngine 1.5 begins by making the project itself a validated engine concept instead of leaving
`swirproject.toml` as scaffolding-only metadata. The Project System 2.0 foundation is intentionally
additive: existing 1.x projects that contain only `name`, `mode`, and `engine` continue to load with
the established `main.py`, `assets`, `scenes`, and `scripts` defaults.

## Public module

```python
from swirengine.project import discover_project, load_project_manifest

project = load_project_manifest(".")
print(project.name, project.mode, project.entrypoint_path)

nearest = discover_project("scripts/gameplay")
print(nearest.root)
```

The initial public surface is:

- `ProjectManifest` — immutable validated project metadata.
- `ProjectDiagnostic` — one deterministic project-layout check.
- `ProjectConfigError` — malformed or unsafe manifest configuration.
- `load_project_manifest(...)` — load from a directory or explicit `swirproject.toml`.
- `discover_project(...)` — walk upward from a nested file/directory to the nearest project.
- `project_diagnostics(...)` — inspect expected project layout without opening the editor.

## Manifest schema 1

New projects use an explicit schema and portable paths:

```toml
schema = 1
name = "ExampleGame"
mode = "3d"
engine = ">=1.0,<2.0"
entrypoint = "main.py"

[paths]
assets = "assets"
scenes = "scenes"
scripts = "scripts"
```

Supported modes are currently `2d` and `3d`. Schema 1 paths are project-relative and may use forward
slashes or Windows-style backslashes; the loader normalizes them to the host platform.

For portability and containment, manifest paths reject:

- POSIX absolute paths;
- Windows drive/root absolute paths;
- UNC paths;
- parent traversal (`..`);
- a bare `.` where a project child path is required.

This is a lexical project-path contract. It does not claim to sandbox arbitrary Python code or
filesystem symlinks created by the project author.

## Backward compatibility

A legacy 1.x manifest remains valid:

```toml
name = "LegacyGame"
mode = "2d"
engine = ">=1.0,<2.0"
```

It is interpreted as schema 1 with:

```text
entrypoint = main.py
assets     = assets
scenes     = scenes
scripts    = scripts
```

No existing `Game`, renderer, scene, editor, or export API is removed or renamed by this milestone.

## Project doctor

`swirengine doctor` discovers the nearest project and reports whether its manifest, entrypoint, and
standard content directories exist:

```bash
swirengine doctor
swirengine doctor path/to/project
```

A healthy project returns exit status `0`. Invalid configuration or missing required layout returns
status `2`, making the command suitable for local scripts and CI.

## Export integration

When `swirengine export` is pointed at a project containing `swirproject.toml`, the manifest supplies
the default application name, entrypoint, and content directories. Explicit command-line overrides
remain authoritative. Projects without a manifest retain the 1.x fallback behavior (`main.py` plus
`assets`, `scenes`, and `scripts`).

Example:

```bash
swirengine export . --target windows
swirengine export . --target linux --entrypoint tools/custom_boot.py
```

## Python 3.10 compatibility

Python 3.11+ provides `tomllib` in the standard library. SwirEngine keeps its supported Python 3.10
baseline by installing `tomli` only on Python versions below 3.11.

## Validation contract

The dedicated Project System 2.0 validation gate covers:

- schema/default compatibility;
- project discovery from nested paths;
- cross-platform path normalization and traversal/absolute-path rejection;
- generated-project round trips;
- deterministic project diagnostics and CLI exit codes;
- manifest-aware export defaults;
- Python 3.10, current stable CI Python, and the project's Python 3.14 compatibility path;
- Ruff, bytecode compilation, and a runnable integration demo.

The SwirEngine 1.4 release remains locked at 100%. Project System 2.0 is post-1.4 development and does
not modify the published 1.4 artifacts.
