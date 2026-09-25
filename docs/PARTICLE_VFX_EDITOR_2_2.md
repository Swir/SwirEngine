# SwirEngine 2.2 Particle / VFX Editor

Milestone 6 builds creator-facing particle and effect authoring on the shipping SwirEngine particle runtimes.

## Current development slice

- Project VFX data is deterministic and stored in `config/vfx.json`.
- Effects select either the shipping CPU 2D particle emitter or the shipping GPU 3D particle emitter.
- Creator presets cover smoke, sparks and a GPU fire baseline while remaining editable.
- Preview controls support start, pause, a real 60 Hz Tk preview loop, bounded stepping, bounded bursts and clear.
- Runtime diagnostics expose capacity, active/queued work, emissions, recycling and bounded work counters; authored capacity is capped at 65,536 particles and manual preview bursts at 4,096.
- Representative source-only 2D and 3D project fixtures save, reopen and exercise the same runtime-backed preview controller used by SwirEditor.
- GPU texture references are project-relative and resolve only below the current project `assets/` directory.

Milestone 6 remains open until the complete acceptance gate in `ROADMAP_2_2.md` is satisfied on an exact head and post-merge `main` evidence is green.
