# SwirEngine 2.0 Runtime Lifecycle Audit

This document records current evidence for **Domain 5 — Runtime stability and resource lifecycle** in the active post-release audit. It is deliberately separate from the historical 2.0 source-development roadmap and does not advance the authoritative audit percentage by itself.

## Scope

The maintained audit harness at [`../tools/audit_runtime_lifecycle_2_0.py`](../tools/audit_runtime_lifecycle_2_0.py) exercises repeated asset-streaming churn, owned preloader shutdown, executor/thread teardown, finalized `AsyncAssetPipeline` request reclamation, worker-failure recovery and cancellation-after-worker-completion. The regression coverage lives in [`../tests/test_post_release_runtime_lifecycle_2_0.py`](../tests/test_post_release_runtime_lifecycle_2_0.py) and [`../tests/test_async_asset_reclamation_2_0.py`](../tests/test_async_asset_reclamation_2_0.py).

The streaming workload repeatedly traverses 32 assets in both directions under a six-asset / 4096-byte residency budget. It verifies that finalized streaming work stays within both configured limits, `release_all(force=True)` returns tracked residency to zero, the shared asset cache no longer retains released streaming assets, and owned asset worker threads are gone after synchronous shutdown.

The preloader workload repeatedly creates and closes owned worker pools and verifies that no pending paths or owned asset worker threads survive `shutdown(wait=True, cancel_futures=True)`.

The async-asset workload repeatedly finalizes successful requests through the public polling path, explicitly reclaims each finalized request, preserves the stable decoded cache, then repeats the same reclamation path for worker failures and cancellation-after-worker-completion. The dedicated API regressions also verify that unfinished work cannot be forgotten and retained dependents prevent dependency reclamation until the dependent records are released first.

## Reclamation contract

`AsyncAssetPipeline.forget(request_id)` is an explicit creator-facing reclamation point for one finalized request. It delegates dependency safety to the maintained `JobScheduler.forget()` contract, removes the matching pipeline/job lookup only after the scheduler accepts reclamation, and returns the finalized `AsyncAssetResult` to the caller.

`AsyncAssetPipeline.prune_finalized(max_items=...)` provides bounded batch reclamation for long-running creator workflows. It removes finalized dependency leaves newest-first, never removes active requests, and leaves any dependency referenced by a retained request in place. Repeated calls can therefore collapse an already-finalized dependency graph without invalidating live dependency relationships.

## Verified closeout evidence

The initial post-release audit found a medium-severity long-session retention issue: finalized pipeline requests and matching terminal scheduler jobs accumulated because the public pipeline had no reclamation path. PR #167 replaced that gap with explicit dependency-safe reclamation and extended deterministic lifecycle coverage to success, worker failure and cancellation outcomes.

The exact implementation head **`0d1c2b65f305ed8b8619dc56fa56435daa4f897a`** completed all **13/13** required pull-request workflows successfully before merge. That matrix included CI, Final Release Gate 2.0, Async Assets 1.7, Source Checkpoints 1.6–1.9, both maintained showcase/hardening workflows, game-demo validation, 3D demo validation, Neon Snake 3D and Desktop Export. PR #167 then merged to `main` as **`cc28b8803138d7ab5f4a7af88ab343de45c85970`**.

The verified harness contract requires, after explicit reclamation and teardown:

- zero retained finalized pipeline request records for the exercised workload;
- zero matching terminal scheduler records after reclamation;
- zero pending async requests;
- bounded streaming residency during churn and zero tracked residency after forced release;
- released streaming assets absent from the shared cache;
- owned preloader/executor worker threads terminated after synchronous shutdown;
- successful, failed and cancelled terminal outcomes reclaimable through the same dependency-safe public contract.

No remaining critical/high-severity or release-blocking Domain 5 finding is known from this evidence. Domain 5 is therefore closed in the authoritative post-release audit. A future lifecycle regression reopens it.

## Verification

Run the focused evidence with:

```bash
pytest -q tests/test_async_asset_reclamation_2_0.py tests/test_post_release_runtime_lifecycle_2_0.py
python tools/audit_runtime_lifecycle_2_0.py
```

The audit command emits deterministic JSON counters and returns non-zero for high-severity lifecycle failures. The repository CI keeps the reclamation tests and lifecycle harness in the maintained Async Assets 1.7 path so later changes cannot silently restore unbounded finalized-request retention.
