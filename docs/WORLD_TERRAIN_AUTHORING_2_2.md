# World/Terrain Authoring — SwirEngine 2.2

Milestone 4 builds creator-facing terrain data on top of the shipping `HeightmapTerrain` and `LargeWorld` runtime systems. The implementation remains source-only until the roadmap acceptance gate is satisfied.

The `.swirterrain` asset model is deterministic and versioned. Sculpting tracks touched terrain chunks, material painting normalizes layer weights, foliage placements remain project-relative, and authored streaming/LOD settings round-trip into runtime configuration.
