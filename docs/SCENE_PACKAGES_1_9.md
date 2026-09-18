# SwirEngine 1.9 — Scene, Prefab & Level Package Workflow

SwirEngine 1.9 Milestone 5 adds a production-facing scene package registry without replacing the
stable `Scene`, `Prefab` or `SceneSerializer` APIs. The goal is to let a real game name its boot
scene, declare packaged levels and reusable prefabs, validate dependency order deterministically and
transition between levels while preserving the runtime `Scene` object owned by the game.

## Manifest contract

Scene shipping is opt-in. Projects without `[scenes]` keep the legacy 1.x behavior unchanged.

```toml
[scenes]
boot = "title"

[scenes.registry.title]
path = "scenes/title.swirscene"
prefabs = []
depends_on = []

[scenes.registry.arena]
path = "scenes/arena.swirscene"
prefabs = ["scenes/crate.swirprefab"]
depends_on = ["title"]
```

The registry is bounded to 256 scene packages. Every package path must stay inside the project;
absolute paths, drive escapes and `..` traversal are rejected before runtime loading. Symlink-resolved
paths are checked again against the project root before files are read.

`depends_on` provides deterministic validation/load ordering. It deliberately **does not merge
scenes or auto-instantiate prefabs**. That keeps scene composition explicit and avoids hidden entity or
object collisions. Dependency cycles, self-dependencies and unknown package names fail before a plan
is accepted.

## Deterministic package plans

```python
from swirengine.project19 import ProjectManifest
from swirengine.scene_packages19 import ScenePackageRegistry

manifest = ProjectManifest.load(".")
registry = ScenePackageRegistry.load_optional(manifest)
assert registry is not None

plan = registry.plan("arena")
print(plan.ordered_packages)
print(plan.fingerprint)
```

Registry and plan fingerprints are portable across checkout locations and independent of TOML table
ordering. They contain only normalized package metadata, never absolute user paths.

## Runtime transitions

```python
from swirengine import Scene, SceneSerializer
from swirengine.project19 import ProjectManifest
from swirengine.scene_packages19 import ScenePackageLoader, ScenePackageRegistry

manifest = ProjectManifest.load(".")
registry = ScenePackageRegistry.load_optional(manifest)
assert registry is not None

scene = Scene()
loader = ScenePackageLoader(registry, SceneSerializer())
loader.transition_to_boot(scene)
loaded = loader.transition(scene, "arena")

crate = loaded.prefabs["scenes/crate.swirprefab"]
crate.instantiate(scene)
```

`transition()` decodes into the existing runtime `Scene` with `clear=True`, so systems that hold the
scene object continue to see the same identity. The declared prefabs are returned as reusable
`Prefab` values and are only instantiated when game code explicitly requests it.

## Validation and custom codecs

`registry.diagnostics()` verifies package paths, missing files, bounded file sizes and symlink
containment without decoding scene objects. This is safe for generic project/export tooling because a
real game may register custom dataclass codecs.

When the creator has the correct codec registry available, full document validation is explicit:

```python
from swirengine import SceneCodecRegistry, SceneSerializer

codecs = SceneCodecRegistry.default()
# codecs.register(MyComponent, name="mygame.MyComponent")
serializer = SceneSerializer(codecs)
diagnostics = registry.validate_documents(serializer)
```

This validates scene/prefab format versions and allow-listed object/component types without dynamic
imports.

## Safety and bounds

- maximum 256 registered scene packages;
- maximum 128 direct dependencies or prefab paths per package;
- maximum 16 MiB per validated/loaded scene or prefab document;
- project-relative manifest paths only, with a second resolved-path containment check;
- deterministic cycle detection and dependency ordering;
- no shell execution, code import or arbitrary class loading from scene JSON;
- no implicit scene composition or prefab spawning.

## Verification

```bash
pytest -q tests/test_scene_packages_1_9.py tests/test_serialization.py tests/test_project_manifest_1_9.py
python examples/demo_scene_packages_1_9.py
python tools/benchmark_scene_packages_1_9.py
ruff check src/swirengine/scene_packages19.py tests/test_scene_packages_1_9.py examples/demo_scene_packages_1_9.py tools/benchmark_scene_packages_1_9.py
python -m compileall -q src/swirengine/scene_packages19.py tests/test_scene_packages_1_9.py examples/demo_scene_packages_1_9.py tools/benchmark_scene_packages_1_9.py
```

The benchmark is a host-side deterministic planning regression contract, not an FPS or runtime load
claim. Milestone 5 remains incomplete until the exact final roadmap-marked head passes its dedicated
Python 3.10/3.13/3.14 gate plus the repository compatibility/runtime/packaging matrix.

`Release/PyPI: frozen until SwirEngine 2.0`.
