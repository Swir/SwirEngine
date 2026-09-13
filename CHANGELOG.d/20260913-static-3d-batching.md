## SwirEngine 1.1 development — static 3D batching

- Added `build_static_cube_batches(...)` for baking visible static `Cube3D` scenery into combined `Mesh3D` batches grouped by compatible color state.
- Added deterministic batching metrics reporting source objects, output batches, draw calls before/after and draw-call reduction ratio.
- Preserved transformed normals with inverse-transpose normal matrices while baking translation, rotation and scale, with pseudo-inverse fallback for degenerate transforms.
- Added regression coverage, creator documentation and a 200-cube demo.
- A same-color 100-cube regression case maps 100 object draws to one renderer-facing mesh draw (99% draw-call reduction by construction).
- Added a CI-gated 1,000-cube CPU frame-preparation benchmark. The verified Ubuntu/Python 3.13 run measured 1,000->1 draw calls and 1,940,573 ns -> 1,950 ns median frame-preparation time (99.90% reduction, 995.35x) for the measured submission component; this is not an end-to-end FPS claim.
- Release/PyPI remains frozen until the active 1.1 roadmap reaches 100%.
