# World/Terrain Authoring — SwirEngine 2.2

Milestone 4 builds creator-facing terrain data on top of the shipping `HeightmapTerrain` and `LargeWorld` runtime systems. The implementation remains source-only until the roadmap acceptance gate is satisfied.

The `.swirterrain` asset model is deterministic and versioned. Sculpting tracks touched terrain chunks, material painting normalizes layer weights, foliage placements remain project-relative, and authored streaming/LOD settings round-trip into runtime configuration.

## Project-scoped terrain assets

`TerrainProjectStore` owns persistence beneath `<project>/assets/terrain`. Creator paths such as `world/main.swirterrain` are resolved inside that root; absolute paths, `..` traversal and non-`.swirterrain` files fail closed. Saves use canonical UTF-8 JSON and replace the target only after the complete payload has been written.

`TerrainAuthoringAsset.from_swirterrain_bytes()` validates the format/version and reconstructs height, material, splat, foliage and streaming data. Serializing an unchanged restored asset yields the same canonical bytes, so project diffs and build inputs remain deterministic.

## Editor workflow

A creator document can be opened or created with `TerrainEditorSession`. The session exposes sculpt/undo/redo, paint, foliage placement, save/reload, a deterministic dirty state and a runtime preview backed by the shipping `HeightmapTerrain` implementation. The editor session never writes outside the terrain asset root.

```python
from swirengine.terrain_authoring22 import (
    TerrainAuthoringAsset,
    TerrainEditorSession,
    TerrainProjectStore,
)

store = TerrainProjectStore(project_root)
session = TerrainEditorSession.create(
    store,
    "world/main.swirterrain",
    TerrainAuthoringAsset.flat(257, 257),
)
session.sculpt(x=64.0, z=64.0, radius=12.0, strength=2.5)
preview = session.runtime_preview()
session.save()
```

Milestone progress remains 3/10 on `main` until the complete M4 exact-head matrix, merge, post-merge validation and formal acceptance evidence are green.
