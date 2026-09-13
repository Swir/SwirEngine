## SwirEngine 1.1 development — static 3D batching

- Added `build_static_cube_batches(...)` for baking visible static `Cube3D` scenery into combined `Mesh3D` batches grouped by compatible color state.
- Added deterministic batching metrics reporting source objects, output batches, draw calls before/after and draw-call reduction ratio.
- Preserved transformed normals with inverse-transpose normal matrices while baking translation, rotation and scale.
- Added regression coverage, creator documentation and a 200-cube demo.
- A same-color 100-cube regression case now maps 100 object draws to one renderer-facing mesh draw (99% draw-call reduction by construction).
- Release/PyPI remains frozen until the active 1.1 roadmap reaches 100%.
