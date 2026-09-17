# Parallel Runtime Showcase — SwirEngine 1.7

SwirEngine 1.7 Milestone 9 is a source-only integration gate for the verified parallel-runtime systems. It does not create a public release and does not change stable 1.x root imports or the published 1.5.0 package metadata.

## Integrated source showcase

`examples/demo_parallel_runtime_showcase_1_7.py` executes the verified creator examples for:

1. bounded background jobs and main-thread handoff;
2. async asset decode/cook;
3. shared resource budgets;
4. streaming work graphs;
5. scene build/activation staging;
6. background save/serialization I/O;
7. shader/material preparation caching;
8. frame-time budgeted owning-thread drains.

The showcase runs those source examples in one interpreter so leaked global state, worker lifecycle mistakes, owning-thread assumptions, and integration regressions surface in addition to the dedicated component tests. It is validated on Linux and Windows with Python 3.13.

## Deterministic soak gate

`tools/soak_parallel_runtime_1_7.py` runs the existing deterministic workload contracts for all eight verified 1.7 runtime systems. Each component keeps its own strict workload contract and the aggregate runner adds a 20-second per-stage timeout plus a generous 30-second total orchestration budget. The aggregate limit is a CI regression guard, not a real-game FPS or latency claim.

The soak process captures each child workload's output and fails with the component name plus stdout/stderr if any workload exits unsuccessfully.

## Cancellation and failure injection

The dedicated milestone workflow runs the complete focused test modules for all eight 1.7 systems on Python 3.10, 3.13 and 3.14. Those suites include the systems' verified cancellation, stale-input, callback failure, rollback, back-pressure and failure-isolation contracts. Milestone 9 therefore validates both the happy-path integrated showcase and the existing negative-path fault contracts on the same candidate line.

## Platform and compatibility gate

Before Milestone 9 can be marked complete, the exact candidate must pass:

- the complete focused 1.7 parallel-runtime regression surface on Python 3.10, 3.13 and 3.14;
- strict Ruff and compile checks for the new integration surfaces;
- the integrated source showcase on Linux and Windows using Python 3.13;
- the deterministic aggregate soak gate on Python 3.13;
- repository-wide CI, Desktop Export, game demos, locked 1.4/1.5 hardening and the 1.6 source checkpoint.

No separate demo GitHub Release is created. Release/PyPI remain frozen until SwirEngine 2.0.
