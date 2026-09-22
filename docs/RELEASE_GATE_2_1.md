# SwirEngine 2.1 Release Gate

This document defines the finite Milestone 10 release-readiness contract for the active
`ROADMAP_2_1.md`. It does not change the published 2.0.0 release, the 10-milestone roadmap
denominator, or the repository release policy.

## Phase A — 9/10 preflight

The release-readiness branch must remain at **9/10 = 90.0%**. This phase proves that the
creator/editor work can be qualified as a complete product candidate without claiming that
Milestone 10 is complete. Phase A **does not publish** SwirEngine 2.1, create a 2.1 tag, change
PyPI package identity, or advance the roadmap to 100%.

The exact preflight head must prove all of the following:

1. `tools/verify_2_1_release_readiness.py` passes.
2. The representative 2D, 3D and multiplayer projects pass the real-game editor gate from
   project creation through authoring, save/reopen, preview/run, diagnostics, Build/Export
   staging and staged runtime validation.
3. The maintained 64-bit CPython 3.10–3.14 Windows/Linux/macOS matrix is requalified against
   the current source rather than inherited from an older release head.
4. Exact-source wheel and sdist artifacts are built, inspected and clean-installed outside the
   development checkout, with representative fixtures executed from the installed package.
5. The Windows CPython 3.14 native renderer dependency path remains explicitly verified rather
   than silently dropping rendering support.
6. Existing public API and compatibility floors remain green; 2.1 editor additions must not
   silently break the published 2.0 game/runtime surface.
7. Performance/scalability evidence stays within committed repository thresholds. No cross-engine
   FPS claim or unmeasured performance gain may be inferred from this gate.
8. Release-safety, artifact-integrity and privacy boundaries remain green.
9. README keeps exactly one deterministic PyPI-safe ASCII progress block generated from
   `ROADMAP_2_1.md`; the GitHub SVG assets remain outside that marked block.
10. Focused tests, strict Ruff and compile validation pass on the exact final preflight head.

A previously green commit is not sufficient after the branch head changes.

### Accepted Phase A evidence

PR #212 exact head `7b7cecb02b0d573d72cc55ec34ecfd307492f3ff` completed all nine
pull-request workflows successfully on 2026-09-22. The dedicated Milestone 10 release-readiness
workflow included the Windows/Linux/macOS CPython 3.10–3.14 matrix, exact-source wheel/sdist
build and clean-install checks, real-game editor regression coverage, public API compatibility,
performance evidence, release-safety validation, strict Ruff and compile checks. This evidence
authorizes Phase B milestone acceptance only; it does not publish SwirEngine 2.1.

## Phase B — Milestone 10 acceptance

Only after Phase A is exact-head green may a dedicated acceptance change mark Milestone 10
complete and move the active roadmap to `10/10 = 100.0%`. That change must cite the accepted
preflight head and preserve all progress math, migration guidance, compatibility evidence,
packaging evidence and supported-platform evidence.

The Phase B acceptance branch must pass its own complete exact-head matrix before merge. Until
that matrix is fully green, `main` remains at the last merged verified state and no publication
claim is allowed.

Reaching 100% means the named 2.1 creator/editor roadmap scope has verified acceptance evidence.
It is not a claim of literal software perfection and it does not itself publish a release.

### Accepted Phase B evidence

PR #213 completed the exact-head acceptance matrix and was merged to `main` as
`09f9b43ef68402f4faa3cd09edad98d859c1bd34`. The resulting `main` then completed its full
post-merge workflow set without failures. The active source roadmap is therefore accepted at
**10/10 = 100.0%**, while public stable remains SwirEngine 2.0.0.

## Phase C — publication decision

Publication is a separate guarded decision after Milestone 10 acceptance. Phase C starts
with a **non-publishing release candidate**. Candidate preparation may set source package metadata
to `2.1.0`, but it must not change README public-stable claims or advertise a PyPI 2.1.0 install
until actual publication and post-publication verification succeed.

The exact release-candidate head must prove all of the following before any tag or upload is
considered:

1. `tools/verify_2_1_release_candidate.py` passes and enforces source version `2.1.0`, accepted
   `10/10 = 100.0%` roadmap math, the PyPI-safe ASCII README exception and non-publishing safety.
2. `tools/verify_2_1_release_readiness.py` still passes on the exact candidate source.
3. `RELEASE_NOTES_2_1.md` accurately describes the candidate and explicitly states that it is not
   yet published.
4. Exact-source wheel and sdist artifacts build successfully and the installed distribution
   reports version `2.1.0`.
5. Clean wheel installs pass on the supported Windows/Linux/macOS CPython 3.10–3.14 matrix,
   including the existing vendored native renderer path for Windows x86-64 CPython 3.14.
6. Candidate workflow permissions remain read-only and contain no PyPI upload, tag creation or
   GitHub Release creation capability.
7. The normal exact-head repository matrix remains green, including representative real-game,
   export/build, compatibility, performance, release-safety and documentation/progress checks.

The release-candidate artifacts are evidence only. They are short-lived workflow artifacts, not
public release assets.

Only after the final candidate head is fully green may a separate publication change introduce
or invoke guarded immutable tag/release/PyPI mechanics. That publication step must bind assets to
the accepted source, generate/check checksums or provenance, preserve existing published tags and
files, and perform public-index post-publication verification before SwirEngine 2.1 is described
as released.

No source-only green CI result may be described as a successful public release.

## Failure policy

Any RED check on a Phase B acceptance or Phase C candidate head blocks merge/publication. Fix the
smallest justified defect, re-run the exact-head matrix, and do not widen feature scope while a
release regression is active. Published tags and release files are immutable.
