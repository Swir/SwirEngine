# Desktop Shipping 1.9

SwirEngine 1.9 adds an additive desktop-shipping contract on top of the existing exporter. It is designed for creators who need a repeatable answer to three questions before publishing a desktop build:

1. **What source content is the build supposed to contain?**
2. **Was the native artifact built on the matching operating system?**
3. **Can the exact produced artifact inventory still be verified after the build?**

This is a source-only 1.9 milestone. It does not publish a SwirEngine 1.9 package or change the release freeze: the next public GitHub Release and PyPI publication remains SwirEngine 2.0.

## Native desktop rule

SwirEngine deliberately does not claim desktop cross-compilation. A Windows profile must be built on Windows, a Linux profile on Linux and a macOS profile on macOS. Planning is portable, but `build_desktop_shipping()` refuses to execute when the selected profile target does not match the current host.

The repository verifies this contract with GitHub-hosted Windows, Linux and macOS runners. Each runner builds a fresh wheel, installs that wheel into a new virtual environment, performs a host-native PyInstaller build, verifies the emitted shipping manifest and executes the packaged smoke application.

## Project profiles

New projects already contain canonical `windows`, `linux` and `macos` packaging profiles. Existing projects can opt in with the same profile syntax:

```toml
[profiles.windows]
target = "windows"
app_name = "MyGame"
onefile = true
console = false

[profiles.linux]
target = "linux"
app_name = "MyGame"
onefile = true
console = false

[profiles.macos]
target = "macos"
app_name = "MyGame"
onefile = true
console = false
```

Only the profile matching the native build host should be executed.

## Deterministic shipping plan

```python
from swirengine.project19 import ProjectManifest
from swirengine.shipping19 import create_desktop_shipping_plan

project = ProjectManifest.load(".")
plan = create_desktop_shipping_plan(project, "linux")
print(plan.fingerprint)
print(plan.to_json())
```

The plan contains the project fingerprint, selected packaging contract, required native host and a sorted source inventory with SHA-256 digests and byte sizes. It contains no checkout-specific absolute paths, so identical project content produces the same plan fingerprint in different checkout directories.

Source paths are bounded and validated. Case-folded path collisions are rejected, as are source symlinks that escape the project root. The shipping layer does not weaken the scene/content-build preflight performed by `ProjectExporter`.

## Host-native build and artifact manifest

```python
from swirengine.project19 import ProjectManifest
from swirengine.shipping19 import build_desktop_shipping

project = ProjectManifest.load(".")
result = build_desktop_shipping(project, "linux")

print(result.plan_path)
print(result.manifest_path)
print(result.manifest.fingerprint)
```

A successful shipping build writes two files beside the existing export manifest:

- `swir-shipping-plan.json` — portable source/build intent;
- `swir-shipping-manifest.json` — target/host identity plus a bounded recursive inventory of the generated native artifacts.

Regular files are recorded with size and SHA-256. Safe in-tree symlinks are represented explicitly by link target, size and SHA-256 of the target text. Symlinks resolving outside the artifact root are rejected.

## Verify an existing artifact tree

```python
from swirengine.shipping19 import verify_desktop_shipping

verify_desktop_shipping(
    "dist/MyGame-linux/swir-shipping-manifest.json",
    plan_path="dist/MyGame-linux/swir-shipping-plan.json",
)
```

Verification fails when an expected artifact is missing, an unexpected file appears, file bytes change, a symlink target changes, the source-plan fingerprint differs or a manifest tries to claim a target/host combination that SwirEngine does not support.

## What reproducible means here

SwirEngine 1.9 promises **reproducible build intent and verifiable inventories**, not bit-for-bit identical executables across operating systems, Python builds or PyInstaller versions. Native packagers may embed platform/toolchain metadata outside SwirEngine's control. The shipping plan is deterministic for identical source content and configuration; the post-build manifest records and verifies the exact bytes actually produced on that native host.

This distinction is intentional and prevents misleading reproducibility or cross-platform claims.

## CI contract

`Desktop Shipping 1.9` is the dedicated milestone workflow. Before this milestone can be marked complete it must pass on the exact implementation head for:

- Ubuntu / Python 3.13;
- Windows / Python 3.13;
- macOS / Python 3.13;
- focused shipping and exporter regressions;
- Ruff and compile checks;
- the deterministic planning workload;
- clean wheel installation into a newly created virtual environment;
- host-native one-file build, shipping-manifest verification and packaged runtime execution.

The normal SwirEngine compatibility/runtime/export gates must then pass on the same exact head before the roadmap checkbox moves to 8/10.
