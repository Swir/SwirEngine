# SwirEngine 1.9 Content Build Graph

SwirEngine 1.9 adds an opt-in, deterministic content graph for projects that need explicit shipping and runtime preparation rules. The graph does **not** replace the stable `AssetManager`, `AssetPreloader`, `AssetStreamingManager`, shader pipeline, scene packages, or 1.6 content-manifest system. It connects them with one production-facing declaration that can be validated before a build is shipped.

The feature is source-only development work on the road to SwirEngine 2.0. It is not a new public release.

## Why this exists

Large projects eventually need answers to four questions that a directory scan cannot provide:

1. Which content depends on which other content?
2. Which inputs should be warmed up, preloaded at startup, or streamed later?
3. Is a required scene, shader, asset, or generated build product missing before packaging starts?
4. Will the shipping profile accidentally exclude content that the game declares as required?

`ContentBuildGraph` answers those questions without moving renderer/GPU work to background threads or changing existing asset-loading semantics.

## Manifest format

The build graph is optional. Projects without `[content.build]` keep their previous 1.x export path.

```toml
name = "Example Game"
mode = "3d"
entrypoint = "main.py"

[content]
include = ["assets", "scripts"]

[[content.build.nodes]]
name = "shader:world"
kind = "shader"
path = "shaders/world.glsl"
# `shader` defaults to load = "warmup"

[[content.build.nodes]]
name = "asset:world"
kind = "asset"
path = "assets/world.bin"
load = "preload"
depends_on = ["shader:world"]

[[content.build.nodes]]
name = "generated:navigation"
kind = "generated"
path = "generated/navigation.bin"
depends_on = ["asset:world"]

[[content.build.nodes]]
name = "scene:level-01"
kind = "scene"
path = "scenes/level-01.swirscene"
depends_on = ["generated:navigation"]
# `scene` defaults to load = "stream"
```

Supported kinds are `asset`, `scene`, `shader`, and `generated`. Supported admission policies are `warmup`, `preload`, and `stream`.

Default policies are deliberately conservative:

| Kind | Default policy | Intended use |
| --- | --- | --- |
| `shader` | `warmup` | shader/material preparation before a hitch-sensitive path |
| `scene` | `stream` | level/content admission on demand |
| `asset` | `preload` | startup or transition-time asset loading |
| `generated` | `preload` | already-produced build data needed by the game |

A creator can explicitly override `load` per node.

## Deterministic dependency planning

```python
from swirengine.content_build19 import ContentBuildGraph
from swirengine.project19 import ProjectManifest

project = ProjectManifest.load(".")
graph = ContentBuildGraph.load_optional(project)
assert graph is not None

plan = graph.plan(["scene:level-01"])
print(plan.ordered_nodes)
print(plan.warmup_paths)
print(plan.preload_paths)
print(plan.stream_paths)
```

The target plan contains the transitive dependency closure in dependency-first order. Fingerprints depend only on portable manifest data, not the checkout directory, so CI and developer machines can compare plans meaningfully.

The graph rejects duplicate node names, duplicate content paths, duplicate dependency entries, unknown dependencies, self-dependencies, dependency cycles, unsafe project paths, empty plans, and invalid enum values. The manifest is bounded to 1,024 nodes and 128 direct dependencies per node.

## Filesystem and shipping preflight

`graph.diagnostics()` checks declared paths against the project root. Symlink paths that resolve outside the project are rejected. Missing content and directory-instead-of-file mistakes are errors.

`graph.shipping_paths()` performs the same preflight and returns all declared files in dependency order only when the graph is shippable.

`ProjectExporter` recognizes a semantic `[content.build]` table and automatically adds those files to the export even when they live outside a profile's generic `include` directories. A profile that tries to exclude required graph content fails before staging begins.

This is important for generated shipping products: a node with `kind = "generated"` names the **output that must already exist when export starts**. SwirEngine does not silently invent or regenerate it during packaging. Build tools can create the file earlier, while the exporter provides a strict final gate.

## Existing runtime integration

The plan connects directly to the established preload and streaming systems:

```python
from swirengine.asset_pipeline import AssetPreloader
from swirengine.asset_streaming import AssetStreamingManager
from swirengine.assets import AssetManager

assets = AssetManager(project.root)
# Register the real project loaders before this point.

with AssetPreloader(assets, max_workers=4) as preloader:
    report = plan.preload_with(preloader)

with AssetStreamingManager(assets) as streaming:
    plan.stage_streaming_with(streaming)
    # Call pump() from the game loop with an appropriate per-frame completion budget.
```

`warmup_paths` remain explicit inputs because shader/material preparation can require renderer-owned context and project-specific variant information. The build graph never moves GPU finalization to a worker thread.

## Relationship to scene packages

Scene packages from Milestone 5 and the content build graph solve different problems:

- scene packages define boot/level scene and prefab relationships;
- content build nodes define broader shipping dependencies and runtime admission policy.

A project may use either system independently or use both. The exporter unions both validated file sets. Duplicate physical content inside the **content build graph itself** is rejected so there is one authoritative node per file.

## Relationship to 1.6 content manifests

`swirengine.content16` remains the integrity, verification, patch-planning, and cache layer. The 1.9 graph provides creator intent and dependency/load planning. A later production step can hash the staged export using the 1.6 manifest primitives without changing either contract.

## Safety and compatibility

- The feature is opt-in through semantic TOML parsing, not textual header scanning.
- Projects without `[content.build]` stay on the established exporter path.
- Malformed legacy manifests do not activate the stricter graph preflight.
- Declared paths cannot be absolute, use parent traversal, or use a drive prefix.
- Resolved symlink escapes fail preflight.
- The graph never executes generated content or arbitrary build commands.
- Renderer/GPU finalization remains owned by the caller/render thread.

## Creator demo

Run `examples/demo_content_build_1_9.py` from a project that declares content-build nodes. The demo prints dependency order and then uses the stable preloader/streaming APIs for the applicable plan groups.

## Verification target

Milestone 6 is considered complete only after the exact candidate head passes its dedicated Python 3.10 / 3.13 / 3.14 gate, the normal CI/export/checkpoint matrix, creator demo execution, deterministic workload benchmark, exporter integration tests, and the roadmap/progress regeneration check. Until then the authoritative SwirEngine 1.9 progress remains at the previously verified milestone count.
