# SwirEngine 1.7 Source Checkpoint Hardening

SwirEngine 1.7 is a source-development checkpoint on the path to SwirEngine 2.0. It must not create a `v1.7.0` tag, GitHub Release or PyPI publication. The published package/runtime version remains 1.5.0 while this source line is developed and verified.

**Release/PyPI: frozen until SwirEngine 2.0**

## Strict completion gate

The final 1.7 candidate must pass:

```bash
python tools/verify_1_7_source_checkpoint.py --require-complete
```

The auditor refuses strict completion unless `ROADMAP_1_7.md` contains exactly 10 checked milestones and the 100.0% / 10/10 marker, the published package/runtime version remains 1.5.0, all verified 1.7 implementation/test/demo/workload/workflow surfaces exist, locked 1.3–1.6 contracts remain complete, the source-only publication policy is intact, and no 1.7 tag/release workflow exists.

## Runtime and compatibility matrix

The exact candidate must re-run the complete focused 1.7 parallel-runtime regression surface on Python 3.10, 3.13 and 3.14. It must also retain the normal repository CI matrix and the locked 1.3, 1.4 and 1.5 compatibility/release contracts plus the strict 1.6 source checkpoint.

The 1.7 gate covers:

- bounded background jobs and main-thread handoff;
- async asset decode/cook and owning-thread finalization;
- shared resource budget accounting/admission;
- streaming work graphs;
- scene build and activation staging;
- background save/serialization I/O;
- shader/material preparation caching;
- frame-time budgeted owning-thread drains;
- the integrated parallel-runtime source showcase and aggregate deterministic soak.

## Integration and fault coverage

`examples/demo_parallel_runtime_showcase_1_7.py` must execute all eight verified 1.7 creator examples in one interpreter. `tools/soak_parallel_runtime_1_7.py` must execute every verified 1.7 workload contract within its explicit orchestration bounds.

The focused suites retain cancellation, stale-input, rollback, callback failure, pressure/back-pressure, failure isolation and owning-thread boundary checks. The source showcase must also run on Linux and Windows so the integration gate does not silently depend on one host platform.

## Packaging and clean install

The final source checkpoint must build the portable wheel and sdist, pass `twine check`, install the wheel into a clean virtual environment, confirm that the installed package reports public version 1.5.0, and run the integrated 1.7 source showcase against that clean installed wheel while the source examples remain outside the wheel.

Repository-wide CI continues to validate the supported OS/Python matrix and the dedicated Windows CPython 3.14 native-wheel path. The locked 1.5 hardening workflow continues to validate headless/real-OpenGL source demos plus Windows one-file packaging/runtime probes.

## Publication invariant

Completion of SwirEngine 1.7 means only that the source checkpoint is verified. It does **not** authorize an intermediate release. After the exact 10/10 checkpoint is green, development proceeds to the next planned source-only stage toward SwirEngine 2.0.

No new public release or PyPI package may be created until the dedicated SwirEngine 2.0 roadmap itself reaches verified 10/10 and its final release gate is green.
