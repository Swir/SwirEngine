# Migrating from SwirEngine 2.1 to 2.2

SwirEngine 2.2.1 is **PUBLISHED** and is the latest public stable release. The immutable
[`v2.2.1` tag and GitHub Release](https://github.com/Swir/SwirEngine/releases/tag/v2.2.1), exact
[PyPI files](https://pypi.org/project/swirengine/2.2.1/), release provenance and public-install
evidence resolve to publication commit `8d27fdb3c37fd79b93a2f3ab420b763de564c9e9`.
The canonical repository record is
[`release-evidence/2.2.1/manifest.json`](../release-evidence/2.2.1/manifest.json).
This guide covers the additive migration from the published 2.1 runtime and creator workflow.
The 2.2.1 maintenance update changes documentation and package metadata only; it does not add a
runtime, public-API or project-data migration beyond the published 2.2.0 feature release.

## Compatibility baseline

- Existing 2.1 projects and the published 2.1 runtime/CLI remain the starting compatibility
  contract.
- The 2.2 visual tools serialize portable project data and call shipping runtime systems; an
  editor-only preview or private mock format is not a migration target.
- Existing Python scripting remains supported. Visual scripting and extension panels add creator
  paths without silently replacing project entry points or trusted Python code.
- The maintained gate continues to cover 64-bit CPython 3.10–3.14 on its explicit hosted
  Windows, Linux and macOS cells. It does not imply support for untested architectures or Python
  implementations.

## Before upgrading a project

Keep the project and its assets under version control, retain a restorable 2.1 copy, then install
the exact public 2.2 release before accepting newly serialized editor data:

```bash
python -m pip install -U "swirengine==2.2.1"
swirengine editor
```

Optional audio support remains an explicit extra:

```bash
python -m pip install -U "swirengine[audio]==2.2.1"
```

Do not publish editor-generated changes until save/reopen, source runtime and relocated export
checks agree. Resource paths must remain project-relative; traversal, absolute aliases and stale
or missing resources are expected to fail closed.

## Additive 2.2 project data

The accepted 2.2 milestones add runtime-backed authoring for materials and shaders, node graphs,
terrain and foliage, animation state machines and blend trees, particle/VFX effects, lighting and
post-FX profiles, responsive UI, and multiplayer/editor diagnostics. These assets should be
reviewed like source code:

- commit canonical project data, not caches, temporary previews or `.swir` editor state;
- preserve the legacy 2.1 runtime path while introducing new assets incrementally;
- reopen the project after each format migration and exercise the shipping runtime bridge;
- keep action labels, extension declarations and visual-graph inputs as data until an explicit
  trusted runtime handler binds them;
- verify default export relocation so no project-checkout path is required at runtime.

The Editor Extension SDK is a capability-gated boundary for trusted installed Python extensions,
not an operating-system sandbox. Review extension code and requested capabilities before enabling
it. Multiplayer debugger captures are bounded diagnostic data and must not contain raw tokens,
payloads, addresses or project paths.

## Updating from 2.2.0 to 2.2.1

No project conversion is required. Install 2.2.1 into the intended environment, reopen the project
and run the same save/reopen, source-runtime and relocated-export checks used for 2.2.0. The update
does not intentionally change serialized formats, runtime behavior or the public Python API.

The maintenance release is bound by the following public evidence:

- source `c2fa0ba9ba4b0a4eb3f1bde0da2e5f8a681e2b7e`, marker
  `47c15f8a4c80318a31762133e0cf4d8524b82564` and publication commit
  `8d27fdb3c37fd79b93a2f3ab420b763de564c9e9`;
- [Publication Gate run `37183101288`](https://github.com/Swir/SwirEngine/actions/runs/37183101288);
- [successful Release run `37183110375`, attempt 2](https://github.com/Swir/SwirEngine/actions/runs/37183110375/attempts/2),
  including clean public installs on Linux, macOS and Windows;
- canonical [`2.2.1 public-release evidence`](../release-evidence/2.2.1/manifest.json), including
  the attempt-scoped authority job identities and exact public asset hashes;
- immutable [`SHA256SUMS`](https://github.com/Swir/SwirEngine/releases/download/v2.2.1/SHA256SUMS)
  and [`release-provenance.json`](https://github.com/Swir/SwirEngine/releases/download/v2.2.1/release-provenance.json).

## Historical Phase B candidate invariants

Before publication, Phase B deliberately required all of the following:

- `ROADMAP_2_2.md` remained **9/10 = 90.0%** and Milestone 10 stayed open;
- `pyproject.toml` and `swirengine.__version__` identified the exact bound candidate as `2.2.0`;
- README continued to identify 2.1.0 as the latest public stable release and pinned public install
  commands to that version;
- `RELEASE_NOTES_2_2.md` and `PYPI_DESCRIPTION_2_2.md` remained publication-ready and
  time-neutral; README carried the temporary non-publication warning instead of embedding it in
  those now-immutable release artifacts;
- no `v2.2.0` tag, GitHub Release, PyPI upload or `.release/publish-2.2.0` marker was created;
- repository-only release evidence and the complete `.release` control directory are excluded
  from wheel and sdist payloads.

These statements remain the historical candidate boundary, not the current release status.

## Historical 2.2.0 Phase E published state

Guarded publication and immutable public verification are complete. `ROADMAP_2_2.md` is now
**10/10 = 100.0%**, `v2.2.0` resolves directly to the publication commit, and the exact public
files passed clean-install checks on Linux, macOS and Windows. The evidence manifest records the
release lineage, both required-workflow manifest identities, all five GitHub Release assets and
the exact successful authority jobs from Release run `37175535837`, attempt 1.

The 10/10 result covers the finite named 2.2 scope. It does not promise literal perfection,
support for unverified platforms or freedom from future focused migration and regression work.

## Verification

The current 2.2.1 maintenance-release contract and preserved 2.2.0 feature-release contract are
checkable with:

```bash
python tools/verify_public_release_2_2_1.py --evidence release-evidence/2.2.1/manifest.json
python tools/verify_required_workflows_2_2.py
python tools/verify_public_release_2_2.py --evidence release-evidence/2.2.0/manifest.json
python tools/verify_distribution_audit_data_2_2.py
python tools/generate_progress_svg.py --check
```

The read-only `.github/workflows/post-release-2.2.1.yml` repeats the 2.2.1 immutable
publication-chain, public metadata, asset and clean-install checks without holding publication
permissions. The historical `.github/workflows/post-release-2.2.yml` continues to protect the
2.2.0 evidence record. See `docs/RELEASE_GATE_2_2.md` for the preserved Phase A–E history, 2.2.1
maintenance-publication evidence and failure policy.
