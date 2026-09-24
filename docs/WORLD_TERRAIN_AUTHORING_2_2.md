# World/Terrain Authoring — SwirEngine 2.2

Milestone 4 builds creator-facing terrain data on top of the shipping `HeightmapTerrain` and `LargeWorld` runtime systems. The implementation remains source-only until the roadmap acceptance gate is satisfied.

The `.swirterrain` asset model is deterministic and versioned. Sculpting tracks touched terrain chunks, material painting normalizes layer weights, foliage placements remain project-relative, and authored streaming/LOD settings round-trip into runtime configuration.

## Project-scoped terrain assets

`TerrainProjectStore` owns persistence beneath `<project>/assets/terrain`. Creator paths such as `world/main.swirterrain` are resolved inside that root; absolute paths, `..` traversal and non-`.swirterrain` files fail closed. Saves use canonical UTF-8 JSON and replace the target only after the complete payload has been written.

`TerrainAuthoringAsset.from_swirterrain_bytes()` validates the format/version and reconstructs height, material, splat, foliage and streaming data. Serializing an unchanged restored asset yields the same canonical bytes, so project diffs and build inputs remain deterministic.

## Unified SwirEditor workflow

`EditorTerrainTooling22` is attached to `EditorIntegratedProjectSession21`, so terrain edits participate in the same dirty/save/close contract as scenes, materials and visual scripts. The `World` menu opens the integrated terrain window in the standard SwirEditor shell.

The terrain window provides project asset creation/selection, a mouse-driven heightmap canvas, raise/lower/flatten/smooth brushes, material-layer painting, foliage placement, undo/redo, reload/save and runtime preview diagnostics. Runtime preview is built from the shipping `HeightmapTerrain` and authored `LargeWorld` streaming settings rather than editor-only mock state.

```python
from swirengine.editor_terrain22 import EditorTerrainPanelController22, EditorTerrainTooling22

terrain = EditorTerrainTooling22(project_root)
panel = EditorTerrainPanelController22(terrain)
panel.create("world/main.swirterrain", width=257, height=257)
panel.sculpt(x=64.0, z=64.0, radius=12.0, strength=2.5)
panel.paint(1, x=64.0, z=64.0, radius=8.0, strength=0.5)
panel.save()
```

Milestone progress remains 3/10 on `main` until the complete M4 exact-head matrix, merge, post-merge validation and formal acceptance evidence are green.
