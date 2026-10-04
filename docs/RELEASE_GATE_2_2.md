# SwirEngine 2.2 Release Gate

This document defines the finite production-acceptance and publication contract for
`ROADMAP_2_2.md`. SwirEngine 2.2.0 is now published and accepted at **10/10 = 100.0%**. The Phase
A–D sections below preserve the boundaries that applied while 2.2 was being qualified; their
temporary 2.1-stable, 9/10 and non-publication statements are historical, not the current status.
A green source branch was necessary evidence, but only immutable public verification and the final
Phase E record authorized the release claim.

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

Phase A evidence is accepted for PR #240. The exact PR head
`6c109e2dce25d94dee91f5b06b84a134e4302d58` completed 54/54 workflows GREEN, including the
explicit required-workflow manifest at 47/47. It was integrated by a normal merge commit, and
fresh `main` at `a634e980649ec50307479ab0d14f483c77315e6a` completed 28/28 push workflows GREEN.
No run IDs are asserted here because they are not part of the recorded evidence.

## Phase B — bound non-publishing candidate

Phase B prepares and qualifies the exact **SwirEngine 2.2.0 bound non-publishing candidate**.
README must state **NOT PUBLISHED**, keep SwirEngine 2.1.0 as the latest public stable release and
keep every public install command pinned to 2.1.0. Package/runtime metadata may now identify
2.2.0, and the primary package roadmap points to `ROADMAP_2_2.md` while all historical roadmap
links remain available.

Candidate artifacts are short-lived evidence and do not authorize a tag, upload, release creation
or public-stable README claim. The candidate source identity, artifact hashes and
supported-platform results must be bound together before publication is enabled.
`RELEASE_NOTES_2_2.md` and `PYPI_DESCRIPTION_2_2.md` are deliberately time-neutral because their
bytes become immutable release metadata; the temporary non-publication warning belongs in README
and the candidate verifier. The roadmap stays at **9/10**.

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

Final Phase E acceptance is complete:

- candidate source `efd5d2b5c26941d49599cd925bb1f8c35b844c3f`, candidate marker
  `48ca4b55b9707845796451136002a4c6568ac231` and publication commit
  `2f150ba6f3fd1e1fd121a8884298e616186e267b` form the verified marker-only chain;
- `v2.2.0` resolves directly to that publication commit, PyPI exposes the exact three
  distributions, and the GitHub Release is server-enforced immutable with the exact five assets;
- Release run `37175535837`, attempt 1, executed trusted workflow commit
  `8cfe640b216c06e5423821615f97828e43b917c6`; all eight authority jobs succeeded, including the
  expanded Linux, macOS and Windows clean public-install cells;
- [`release-evidence/2.2.0/manifest.json`](../release-evidence/2.2.0/manifest.json) is the canonical
  versioned record of the lineage, publication and Phase E workflow-manifest digests, logical
  sdist, immutable metadata, public asset identities and attempt-scoped job identities;
- `.github/release-gates/2.2-required-workflows.json` replaces only the historical candidate gate
  entry with `Post-release 2.2 Public Verification`; the publication-time manifest remains bound
  by its immutable candidate-source digest;
- `tools/verify_public_release_2_2.py` and `.github/workflows/post-release-2.2.yml` re-read the
  public state and verify it without publication permissions.

The roadmap therefore advances to **10/10 = 100.0%** and README identifies 2.2.0 as the latest
public stable release. Before this acceptance, both documents correctly remained at 9/10 even
after partial or misleadingly green publication attempts. Completion applies only to the finite
ten-milestone Production Tools & Visual Creation contract; it is not a claim of literal perfection
or universal platform support.

## Failure policy

Any missing, skipped, cancelled, stale or red required check blocks advancement. Fix only the
smallest justified defect, then run the complete matrix on the new exact head. Published tags,
PyPI files and GitHub Release assets are immutable; a conflict is a hard stop, not permission to
overwrite or delete public state.
