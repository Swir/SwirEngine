# Migrating from SwirEngine 2.0 to 2.1

SwirEngine 2.1 is currently **source development**, not a published package. The latest public
stable release remains **SwirEngine 2.0.0**. This guide records the intended migration boundary
for the active 2.1 SwirEditor/creator workflow so compatibility can be verified before any future
publication decision.

## Compatibility baseline

- Existing 2.0 game/runtime projects remain the compatibility starting point.
- Published 2.0 APIs must not be removed or silently reinterpreted by editor-only work.
- New 2.1 creator/editor surfaces are additive unless a deliberate migration is documented and
  covered by regression tests.
- The maintained runtime range remains 64-bit CPython 3.10–3.14 on the Windows/Linux/macOS cells
  that are explicitly reverified by CI; this is not a claim for unsupported interpreters or
  architectures.

## Project workflow

A 2.0 project can continue to run through the runtime/CLI path. To exercise the 2.1 creator flow
from source development:

```bash
git clone https://github.com/Swir/SwirEngine.git
cd SwirEngine
python -m pip install -e ".[dev]"
swirengine editor
```

The editor stores creator state in project-owned data and uses the shipping runtime systems for
scene, asset, gameplay and export behavior. Keep project source under version control before
migrating editor-authored data so scene, prefab and project-setting changes can be reviewed.

## Build and export

The 2.1 Build/Export Wizard stages projects through the same shipping/export foundations verified
by the repository gates. A successful editor export is not a substitute for the release-readiness
matrix: wheel/sdist clean installs, supported-platform probes and representative 2D/3D/multiplayer
staged runtimes must also pass.

## What is not changing during preflight

While Milestone 10 is open:

- `pyproject.toml` remains at the published stable package identity `2.0.0`;
- no `v2.1.0` tag or PyPI publication is created;
- `ROADMAP_2_1.md` remains the authoritative development source at **9/10 = 90.0%**;
- README keeps its single PyPI-safe ASCII progress block synchronized from that roadmap;
- published 2.0 tags and artifacts remain immutable.

## Verification

Before Milestone 10 can close, the exact candidate head must pass the real-game editor gate,
current compatibility/public-API checks, packaging and clean-install checks, performance evidence,
release-safety checks and the supported Windows/Linux/macOS CPython matrix defined by
`docs/RELEASE_GATE_2_1.md`.
