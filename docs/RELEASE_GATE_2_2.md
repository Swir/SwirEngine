# SwirEngine 2.2 Release Gate

This document defines the finite production-acceptance and publication contract for
`ROADMAP_2_2.md`. SwirEngine 2.2.0 remains the immutable feature release accepted at
**10/10 = 100.0%**, and metadata-only maintenance release **2.2.1 is now the latest public stable
package**. The Phase A–E sections preserve the boundaries and evidence that applied while 2.2.0
was being qualified and published; the dedicated 2.2.1 section records the later maintenance
publication. A green source branch was necessary evidence, but only immutable public verification
authorized either release claim.

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
README must carry an explicit non-publication warning, keep SwirEngine 2.1.0 as the latest public
stable release and keep every public install command pinned to 2.1.0. Package/runtime metadata may
now identify 2.2.0, and the primary package roadmap points to `ROADMAP_2_2.md` while all historical
roadmap links remain available.

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

At the 2.2.0 Phase E acceptance, the roadmap advanced to **10/10 = 100.0%** and README identified
2.2.0 as the latest public stable release. Before that acceptance, both documents correctly
remained at 9/10 even after partial or misleadingly green publication attempts. Completion applies
only to the finite
ten-milestone Production Tools & Visual Creation contract; it is not a claim of literal perfection
or universal platform support.

## SwirEngine 2.2.1 metadata-only maintenance publication

SwirEngine 2.2.1 carries the accepted 2.2 runtime, public API, project data and 10/10 roadmap scope
forward without functional changes. Its release change is the complete package-index description
and matching release metadata. Existing 2.2.0 projects require no data migration.

The final public state is verified as follows:

- [`release-evidence/2.2.1/manifest.json`](../release-evidence/2.2.1/manifest.json) is the canonical
  repository-owned record of lineage, exact assets, attempt-scoped authority jobs and both
  publication/Phase E workflow-manifest identities;
- candidate source `c2fa0ba9ba4b0a4eb3f1bde0da2e5f8a681e2b7e`, candidate marker
  `47c15f8a4c80318a31762133e0cf4d8524b82564` and publication commit
  `8d27fdb3c37fd79b93a2f3ab420b763de564c9e9` form the marker-only chain recorded in the published
  [`release-provenance.json`](https://github.com/Swir/SwirEngine/releases/download/v2.2.1/release-provenance.json);
- [`v2.2.1`](https://github.com/Swir/SwirEngine/releases/tag/v2.2.1) is a direct tag to that
  publication commit, and the GitHub Release is server-enforced immutable, non-draft and
  non-prerelease;
- [Publication Gate run `37183101288`, attempt 1](https://github.com/Swir/SwirEngine/actions/runs/37183101288)
  accepted the exact publication commit;
- [Release run `37183110375`, attempt 2](https://github.com/Swir/SwirEngine/actions/runs/37183110375/attempts/2)
  executed trusted workflow head `3577e2fc25e3bf1604630a844851b5052abc7639` and completed all
  32 jobs with 30 successes, two intentional skips and no failures;
- the tag write job
  [`111381182146`](https://github.com/Swir/SwirEngine/actions/runs/37183110375/job/111381182146)
  took its idempotent read-back path because the exact tag already existed; the GitHub Release
  writer [`111381243165`](https://github.com/Swir/SwirEngine/actions/runs/37183110375/job/111381243165)
  and PyPI writer
  [`111381335658`](https://github.com/Swir/SwirEngine/actions/runs/37183110375/job/111381335658)
  were skipped rather than duplicating immutable public objects;
- fresh tag, GitHub Release and PyPI reconciliation succeeded, followed by clean public-index
  installs on [Linux / CPython 3.13](https://github.com/Swir/SwirEngine/actions/runs/37183110375/job/111381365661),
  [macOS / CPython 3.13](https://github.com/Swir/SwirEngine/actions/runs/37183110375/job/111381365706)
  and [Windows / CPython 3.14](https://github.com/Swir/SwirEngine/actions/runs/37183110375/job/111381365690);
- the final
  [immutable tag, release, package and evidence job](https://github.com/Swir/SwirEngine/actions/runs/37183110375/job/111381456957)
  succeeded.

The GitHub Release and PyPI expose the same three distributions:

| File | Size | SHA-256 |
|---|---:|---|
| `swirengine-2.2.1-py3-none-any.whl` | 830462 bytes | `e61be3dbe011ff6035b65111e99478127b918f57f900c6803e3d649a44a41379` |
| `swirengine-2.2.1-cp314-cp314-win_amd64.whl` | 948619 bytes | `4ee9257831aab322f9da220feebe01fc25ecb8e5191f0a3ead0a2933a0304f1b` |
| `swirengine-2.2.1.tar.gz` | 2925167 bytes | `e1505898990d98d33a8f83075933220b87a3e2fe1269f77bfdd350f02a27915c` |

The remaining immutable assets are `SHA256SUMS` (299 bytes,
`1cbc2f69adae97fd7b74ff828ba24768beeaf5f5f5e634421a72962e1a4e7e7d`) and
`release-provenance.json` (1064 bytes,
`d67ff60c0694f1229a1261bb9a267c28dfd911a31e96d77262f3ff44b1b4ce8c`).

The canonical evidence records publication workflow-manifest digest
`d75b8dbd9afed9b6fe4df7892dbebcd009ea57bd87e0c1de8046085bc7b56d0a`, Phase E
workflow-manifest digest `a04ea73f89974ee4e0d58d132cad0c849a492bc6615788174a305b407bef2eb0`
and logical-sdist digest `0329fbfcfdd42364091a72e8d0808f2d584793a13ac5fd366f11a8e03ffdd27d`.
The immutable [`SHA256SUMS`](https://github.com/Swir/SwirEngine/releases/download/v2.2.1/SHA256SUMS)
is the compact public checksum manifest. The repository-owned 2.2.0 evidence remains preserved and
continues to describe that earlier feature release rather than being rewritten as 2.2.1 evidence.

## Failure policy

Any missing, skipped, cancelled, stale or red required check blocks advancement. Fix only the
smallest justified defect, then run the complete matrix on the new exact head. Published tags,
PyPI files and GitHub Release assets are immutable; a conflict is a hard stop, not permission to
overwrite or delete public state.
