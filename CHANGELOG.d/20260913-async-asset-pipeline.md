## SwirEngine 1.1 development — async/preload asset pipeline

- Added bounded background asset loading with `AssetPreloader.load_async(...)` and whole-batch `preload_async(...)` APIs layered on the existing `AssetManager` cache/loader system.
- Added deterministic per-resource and per-batch diagnostics: canonical path, cache-hit state, loader duration, wall time, isolated errors and an explicit loading-wait reduction ratio.
- Duplicate requests for the same canonical path now share one in-flight load in the preloader, avoiding duplicate decode work during scene transitions.
- Batch failures are isolated so one broken resource does not discard successful loads from the same preload transaction.
- Added creator documentation, an async loading example, regression coverage and a CI-gated synthetic I/O benchmark that verifies concurrent preload reduces serialized loading wait without making an FPS claim.
- GPU/context-owned finalization remains explicitly on the render thread; the background stage targets file I/O, parsing, decompression and thread-safe CPU-side decoding.
- Advanced `ROADMAP_1_1.md` to 4/10 (40.0%) after implementation and verification. Release/PyPI remains frozen until 10/10.
