# SwirEngine 2.2 Release Gate

This document defines the finite production-acceptance and publication contract for
`ROADMAP_2_2.md`. It preserves the published SwirEngine 2.1.0 package, tag and public evidence
while 2.2 is still being qualified. A green source branch is necessary evidence, not a public
release claim.

## Phase A — 9/10 exact-source preflight

Phase A must remain at **9/10 = 90.0%**. Package metadata, runtime metadata and public install
instructions remain **2.1.0**. This phase must not create a `v2.2.0` tag, a GitHub Release, a PyPI
upload or `.release/publish-2.2.0` publication marker.

The exact Phase A head must prove all of the following:

1. `tools/verify_2_2_release_readiness.py` passes and confirms the roadmap, README, package and
   runtime are still in the 9/10 / stable-2.1.0 state.
2. `.github/release-gates/2.2-required-workflows.json` passes
   `tools/verify_required_workflows_2_2.py`; required checks are identified by their explicit
   workflow names, never by an aggregate count alone.
3. The representative 2D, 3D and multiplayer projects remain green through authoring,
   save/reopen, runtime preview, diagnostics, build/export staging and relocated staged runtime.
4. The maintained 64-bit CPython 3.10–3.14 Windows/Linux/macOS matrix is rebuilt from the exact
   head. Windows CPython 3.14 retains its explicit vendored-native dependency check.
5. An exact-source wheel and sdist are built and inspected. Neither artifact may contain
   repository-only `release-evidence` data or any `.release` control data, including case,
   separator, traversal and Windows trailing-dot/space aliases.
6. Every clean-wheel job supplies `--expected-version 2.1.0`, so both installed distribution
   metadata and `swirengine.__version__` are checked rather than inferred from the filename.
7. Published API compatibility, packaging/shipping, performance evidence and release-safety
   boundaries remain green without inventing cross-engine performance or public-network claims.
8. README keeps exactly one deterministic PyPI-safe ASCII progress block generated from
   `ROADMAP_2_2.md`; public installation stays pinned to 2.1.0.
9. The readiness workflow checks out the pull-request head SHA (or its explicit dispatch SHA),
   disables persisted credentials and declares only `contents: read` permission.
10. Focused tests, strict Ruff, compile validation, YAML parsing and the normal exact-head
    repository matrix pass after the final Phase A change.

Phase A evidence: pending exact-head CI. Record an exact 40-character head and its complete green
workflow evidence only after that unchanged head finishes; do not copy evidence from an ancestor.

## Phase B — bound non-publishing candidate

After Phase A is accepted, Phase B may prepare and qualify the exact 2.2.0 candidate source. It
must remain non-publishing: candidate artifacts are short-lived evidence and do not authorize a
tag, upload, release creation or public-stable README claim. The candidate source identity,
artifact hashes and supported-platform results must be bound together before publication is
enabled. The roadmap stays at **9/10**.

## Phases C and D — guarded publication and immutable verification

Publication is a separately reviewed operation using the established `.github/workflows/release.yml`
identity. It must use an explicit required-workflow manifest for the accepted source SHA, generate
artifacts from that source, and fail closed on any source, version, tag, asset or provenance
mismatch. Retry/resume behavior may fill a missing public object only when every existing PyPI,
tag and GitHub Release identity is already consistent; it must never replace a conflicting object.

The publication branch uses two deterministic marker-only commits `C → M1 → P` under the excluded
`.release/publish-2.2.0/` directory. A read-only publication gate validates the exact same-repo
`push` at `P`; the Trusted Publisher workflow starts only from that successful `workflow_run` and
rechecks its event, workflow path, repository, branch and head SHA. The accepted `C` must be the
reviewed head of exactly one merged same-repository PR and remain reachable through its merge
commit from fresh `main`. The `v2.2.0` tag, wheel, sdist, checksums, provenance and GitHub Release
assets must all resolve to the same logical source. Public-index verification must use a clean
environment and immutable public artifacts, not the checkout or workflow cache. The roadmap stays
at **9/10** while any part of publication or public verification is pending.

## Phase E — final evidence and roadmap acceptance

Phase E records the immutable tag/source identity, public PyPI metadata, GitHub Release asset
hashes, clean public installation results and exact successful post-release workflow evidence.
The evidence must be durable repository data but excluded from wheel and sdist payloads.

Only final Phase E acceptance may advance the roadmap to 10/10 = 100.0%. That change must run its
own exact-head required workflow set and the resulting merged `main` SHA must also finish green.
Until then, README and `ROADMAP_2_2.md` must continue to report 9/10, even if an earlier release
operation succeeded.

## Failure policy

Any missing, skipped, cancelled, stale or red required check blocks advancement. Fix only the
smallest justified defect, then run the complete matrix on the new exact head. Published tags,
PyPI files and GitHub Release assets are immutable; a conflict is a hard stop, not permission to
overwrite or delete public state.
