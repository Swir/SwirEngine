# Migrating from SwirEngine 2.1 to 2.2

SwirEngine 2.2.0 is a **bound non-publishing candidate** and is **NOT PUBLISHED**. The latest
public stable release remains **SwirEngine 2.1.0**. This guide describes the additive
production-tools boundary being qualified before the guarded 2.2 publication decision; it is not
an instruction to install 2.2.0 from a public package index.

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

## Before opening a project from source

Keep the project and its assets under version control, then test the unchanged project against the
2.2 source checkout before accepting newly serialized editor data:

```bash
git clone https://github.com/Swir/SwirEngine.git
cd SwirEngine
python -m pip install -e ".[dev]"
swirengine editor
```

For production installs, continue to use the public stable release:

```bash
python -m pip install -U "swirengine==2.1.0"
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

## Phase B candidate invariants

While the release gate is in Phase B:

- `ROADMAP_2_2.md` remains **9/10 = 90.0%** and Milestone 10 stays open;
- `pyproject.toml` and `swirengine.__version__` identify the exact bound candidate as `2.2.0`;
- README continues to identify 2.1.0 as the latest public stable release and pins public install
  commands to that version;
- `RELEASE_NOTES_2_2.md` and `PYPI_DESCRIPTION_2_2.md` remain publication-ready and
  time-neutral; README carries the temporary non-publication warning instead of embedding it in
  immutable release artifacts;
- no `v2.2.0` tag, GitHub Release, PyPI upload or `.release/publish-2.2.0` marker is created;
- repository-only release evidence and the complete `.release` control directory are excluded
  from wheel and sdist payloads.

Roadmap completion is intentionally later than source preflight. Only final Phase E evidence after
guarded publication and immutable public verification may advance Milestone 10 to 10/10.

## Verification

The local bound-candidate contract can be checked with:

```bash
python tools/verify_required_workflows_2_2.py
python tools/verify_2_2_release_candidate.py
python tools/verify_distribution_audit_data_2_2.py
python tools/generate_progress_svg.py --check
```

The dedicated `.github/workflows/release-candidate-2.2.yml` additionally rebuilds exact-source
artifacts and clean-installs the wheel across the supported matrix with the explicit expected
candidate version. See `docs/RELEASE_GATE_2_2.md` for the evidence order and failure policy.
