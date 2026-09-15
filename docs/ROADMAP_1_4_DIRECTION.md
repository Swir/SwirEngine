# SwirEngine 1.4 Direction

SwirEngine 1.4 is the **Production World & Engine Power** line.

The goal is not to accumulate unrelated features. The release should deepen the systems that matter for larger, more polished games while preserving the stable 1.x public API.

## Competitive direction

SwirEngine 1.4 should close practical gaps versus mature Python game engines by improving:

- terrain and world authoring
- deeper physics and character movement
- modern rendering and VFX
- asset import throughput and hot reload
- spatial scene scaling and visibility work
- editor authoring ergonomics
- multiplayer replication and latency handling

## Milestone rules

Each milestone must include:

1. production implementation
2. focused regression tests
3. measurable performance/diagnostic contracts where relevant
4. an example or integrated demo path
5. README/ROADMAP/CHANGELOG synchronization
6. dedicated CI/runtime validation when the feature depends on graphics, packaging or platform behavior

SwirEngine 1.3.0 remains the stable public release until the 1.4 roadmap reaches exactly 10/10 = 100.0% and the final public-install release gate succeeds.
