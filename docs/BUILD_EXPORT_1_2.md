# Build / export hardening — SwirEngine 1.2

SwirEngine 1.2 turns the existing deterministic export staging layer into an explicit, verifiable desktop shipping workflow while keeping the public 1.x API backward compatible.

## Staging remains the default

`ProjectExporter.export()` still performs no implicit third-party installation or native compilation. It copies the selected project files into a deterministic staging directory and writes `swir-export.json`.

Desktop staging now additionally produces `swirengine-build.spec`, a portable PyInstaller spec generated from the same `PackagingProfile`. The manifest format is version 2 and records SHA-256 checksums for every staged project file so CI or release tooling can detect changed/missing inputs.

```python
from swirengine import ExportTarget, PackagingProfile, ProjectExporter

profile = PackagingProfile(
    name="my-game",
    target=ExportTarget.WINDOWS,
    onefile=True,
)
result = ProjectExporter(".").export(profile)
print(result.manifest)
print(result.native_spec)
```

## Explicit native builds

Native compilation is opt-in:

```python
build = ProjectExporter(".").build_native(profile)
for artifact in build.artifacts:
    print(artifact)
```

or from the CLI:

```text
swirengine export . --target windows --onefile --build-native
```

`build_native()` intentionally requires a matching host:

- Windows target → Windows host
- Linux target → Linux host
- macOS target → macOS host

SwirEngine does not pretend PyInstaller can safely cross-compile these desktop targets. The selected build environment must already contain PyInstaller; SwirEngine does not install build tools implicitly.

## Project data and dynamic scripts

The generated spec carries staged assets, scenes, project metadata and dynamically loaded project scripts as PyInstaller data. The game entrypoint is handled by PyInstaller's analysis phase, while other source files selected through `PackagingProfile.include` remain available for engines or games that load scripts by path at runtime.

Paths that are absolute or contain `..` are rejected for entrypoints, includes and icons. This prevents an export profile from escaping the project root and accidentally staging unrelated host files.

## One-file and one-directory outputs

Both shipping modes are part of the desktop gate:

- `onefile=True` embeds Python code, dependencies and staged project data in one executable;
- the default one-directory mode emits an executable plus its dependency directory.

The CLI keeps staging-only export as the default so existing workflows do not unexpectedly execute native build tools.

## Verification contract

`.github/workflows/desktop-export.yml` performs real native shipping smoke tests on `ubuntu-latest`, `windows-latest` and `macos-latest` with Python 3.13. Each host:

1. installs SwirEngine plus PyInstaller;
2. creates a minimal project that imports the installed engine;
3. bundles a real asset and a dynamically loaded Python script;
4. builds a one-file executable and runs it;
5. builds a one-directory executable and runs it;
6. requires the packaged executable to read both staged resources and emit a known success marker.

This is stronger than merely generating a command or spec: the artifact itself must start successfully on the target OS. Windows Python 3.14 engine-package support remains separately guarded by the existing native-wheel CI job and is not claimed as a desktop-export shipping configuration unless the shipping workflow explicitly verifies it.

## Manifest integrity

`swir-export.json` version 2 contains:

- target and app metadata;
- deterministic staged file ordering;
- SHA-256 for every staged input;
- the generated native spec name;
- the explicit build command;
- experimental status for non-desktop staging targets.

Android and Web remain experimental staging exports. This milestone does not claim production-ready mobile/web shipping.
