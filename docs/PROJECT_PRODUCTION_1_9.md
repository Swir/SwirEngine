# Project Production Workflow — SwirEngine 1.9

SwirEngine 1.9 starts the production/shipping phase on top of the completed 1.8 rendering checkpoint.
Milestone 1 makes `swirproject.toml` an actual validated project contract instead of a passive starter
file. The feature remains additive: existing minimal manifests and explicit `swirengine export
--target ...` commands continue to work.

## Starter manifest

`swirengine new MyGame --mode 3d` creates a project with an immediately valid manifest, three content
directories and named desktop packaging profiles:

```toml
name = "MyGame"
mode = "3d"
engine = ">=1.0,<2.0"
entrypoint = "main.py"

[content]
include = ["assets", "scenes", "scripts"]

[profiles.windows]
target = "windows"
app_name = "MyGame"
onefile = false
console = true

[profiles.linux]
target = "linux"
app_name = "MyGame"
onefile = false
console = true

[profiles.macos]
target = "macos"
app_name = "MyGame"
onefile = false
console = true
```

A `[project]` table is also accepted for richer hand-written manifests. Root-level project keys remain
supported so projects created by earlier SwirEngine versions do not need a migration just to load.

## Validate before running or shipping

Run:

```bash
swirengine doctor .
```

or validate one packaging profile:

```bash
swirengine doctor . --profile windows
```

The command checks the manifest, entrypoint and profile icon paths, reports missing optional content
roots as warnings, and prints the deterministic manifest fingerprint. It does not modify project data.

All manifest-controlled paths must remain project-relative. Absolute paths, `..` traversal, Windows
drive escapes and UNC-style paths are rejected before they can reach the exporter.

## Export from a named profile

A project can now stage an export directly from its production profile:

```bash
swirengine export . --profile windows
```

For a native build on a matching desktop host:

```bash
swirengine export . --profile windows --build-native
```

SwirEngine still refuses desktop cross-compilation. Windows builds belong on Windows, Linux builds on
Linux and macOS builds on macOS. Profile-driven export delegates to the established
`PackagingProfile`/`ProjectExporter` implementation, so checksums, staging manifests and PyInstaller
spec generation retain their existing behavior.

Explicit-target export remains available for scripts and older projects:

```bash
swirengine export . --target linux
```

## Profile fields

A profile supports the existing production/export contract:

- `target`: `windows`, `linux`, `macos`, `android` or `web`;
- `entrypoint`: project-relative Python entrypoint, inherited from the project when omitted;
- `app_name`: packaged application name;
- `include` / `exclude`: bounded arrays of project-relative paths;
- `icon`: optional project-relative icon;
- `onefile`: request a one-file PyInstaller desktop plan;
- `console`: keep or suppress the console for desktop builds;
- `[profiles.<name>.metadata]`: bounded string metadata copied into the export manifest.

Android and Web remain experimental staging targets; a profile does not upgrade their support status.

## Determinism and compatibility

`ProjectManifest.fingerprint` hashes the normalized semantic manifest rather than its checkout path.
This gives build tooling a stable identity for equivalent project configurations on different
machines. The 1.9 workflow verifies Python 3.10, 3.13 and 3.14 and runs legacy CLI/export regressions
alongside the new manifest tests.

SwirEngine 1.9 is source-only. No 1.9 GitHub Release, release tag or PyPI publication is created.
