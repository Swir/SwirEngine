# SwirEngine 2.0 Runtime Lifecycle Audit

This document records current evidence for **Domain 5 — Runtime stability and resource lifecycle** in the active post-release audit. It is deliberately separate from the historical 2.0 source-development roadmap and does not advance the authoritative audit percentage by itself.

## Scope

The maintained audit harness at [`../tools/audit_runtime_lifecycle_2_0.py`](../tools/audit_runtime_lifecycle_2_0.py) exercises repeated asset-streaming churn, owned preloader shutdown, executor/thread teardown and finalized `AsyncAssetPipeline` request retention. The regression coverage lives in [`../tests/test_post_release_runtime_lifecycle_2_0.py`](../tests/test_post_release_runtime_lifecycle_2_0.py).

The streaming workload repeatedly traverses 32 assets in both directions under a six-asset / 4096-byte residency budget. It verifies that finalized streaming work stays within both configured limits, `release_all(force=True)` returns tracked residency to zero, the shared asset cache no longer retains released streaming assets, and owned asset worker threads are gone after synchronous shutdown.

The preloader workload repeatedly creates and closes owned worker pools and verifies that no pending paths or owned asset worker threads survive `shutdown(wait=True, cancel_futures=True)`.

The async-asset workload finalizes repeated requests through the public polling path and verifies zero pending requests plus a stable one-entry decoded cache for an unchanged source.

## Current finding

The first deep-lifecycle pass identified one **medium-severity retention issue** that keeps Domain 5 open: finalized `AsyncAssetPipeline` request records and the corresponding terminal `JobScheduler` records remain retained for the lifetime of the pipeline. `JobScheduler` already has an explicit `forget()` contract after outcome delivery, but `AsyncAssetPipeline` does not currently expose a creator-facing reclamation path and therefore cannot release its matching request bookkeeping safely through public API.

This is not being classified as a release-blocking correctness failure: workers terminate cleanly, streaming residency returns to zero when explicitly released, no owned asset threads remain after synchronous shutdown, and completed async requests are no longer pending. It is nevertheless a real long-session memory-growth risk for creator workflows that continuously submit and finalize many distinct requests.

## Required closeout work

Domain 5 remains incomplete until the retained terminal-request lifecycle has a safe reclamation path and the audit is rerun against that implementation. The preferred fix must preserve dependency correctness: a request cannot be forgotten while retained dependents still reference it. After that fix, broaden the same evidence to failure/cancellation recovery and representative runtime workloads before marking the domain complete.

Run the audit locally with:

```bash
python tools/audit_runtime_lifecycle_2_0.py
```

The command emits deterministic JSON counters and returns non-zero only for high-severity lifecycle failures. Medium findings remain visible without hiding the rest of the audit evidence.
