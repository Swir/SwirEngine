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

## Current evidence

The previous audit found a medium-severity long-session retention issue: finalized pipeline requests and matching terminal scheduler jobs accumulated because the public pipeline had no reclamation path. The current hardening branch replaces that finding with explicit dependency-safe reclamation and expands the deterministic lifecycle harness to success, failure and cancellation outcomes.

This change does **not** advance Domain 5 merely because the API exists. The domain remains open until the exact final branch head passes the repository test/CI matrix and the updated lifecycle harness proves zero retained pipeline request records, zero terminal scheduler records after reclamation, zero pending async requests, bounded streaming residency, clean cache release and clean owned-thread teardown.

## Verification

Run the focused evidence with:

```bash
pytest -q tests/test_async_asset_reclamation_2_0.py tests/test_post_release_runtime_lifecycle_2_0.py
python tools/audit_runtime_lifecycle_2_0.py
```

The audit command emits deterministic JSON counters and returns non-zero for high-severity lifecycle failures. A clean run after the reclamation fix must report no findings.
