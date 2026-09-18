# SwirEngine 2.0 API and Migration Contract

SwirEngine 2.0 is the next public release after 1.5.0. Source-only checkpoints 1.6–1.9 are development history, not public package versions. This document defines how the 2.0 line can evolve the engine without silently breaking existing 1.x projects.

## Locked public baseline

The released `v1.5.0` root API is the migration baseline. The canonical snapshot lives in `docs/api-contracts/swirengine-1.5-public-api.json` and contains exactly 271 names exported through `swirengine.__all__` plus a SHA-256 over the ordered export list.

The baseline is data, not a generated guess from current source. Editing it to make a breaking change pass is forbidden. A legitimate 2.0 change must be recorded in the separate migration ledger.

## Migration ledger

`docs/api-contracts/swirengine-2.0-migration.json` is the machine-readable 1.5.0 → 2.0.0 ledger.

- `graduated_exports` lists new names intentionally promoted to the root public API.
- `removals` lists baseline root exports intentionally removed for 2.0. Every removal requires a migration rationale and may name a public replacement.
- A name cannot be both graduated and removed.
- Undocumented root additions or removals fail the gate.
- A documented replacement must actually be public in the candidate surface.

The initial ledger is empty: 2.0 development starts with the released 1.5.0 root surface intact. Source-only systems are not automatically promoted merely because they exist in the repository.

## Source-development version freeze

Until the final 2.0 release-candidate transition, both `swirengine.__version__` and `[project].version` remain `1.5.0`. This prevents intermediate source checkpoints from masquerading as published package versions.

The verifier has an explicit `--release-candidate` mode. That mode requires both version surfaces to be exactly `2.0.0` and is reserved for the final 2.0 release gate after the dedicated roadmap reaches its verified completion criteria.

## Verification

Run the development contract locally with:

```bash
python tools/verify_api_contract_2_0.py
python tools/verify_api_contract_2_0.py --json
```

The verifier parses `src/swirengine/__init__.py` statically, so checking the root API does not import renderer, audio, networking or editor backends. It rejects duplicate/unbound `__all__` entries, baseline corruption, undeclared additions/removals, invalid replacements and package-version drift.

The dedicated 2.0 API workflow runs the contract on Python 3.10, 3.13 and 3.14 and also re-runs the strict completed 1.9 source checkpoint. A 2.0 API migration is not considered verified until the exact final head passes the wider compatibility/runtime/packaging gates required by the active roadmap.

## Creator-facing migration standard

Breaking changes are allowed only where they materially improve a coherent 2.0 creator workflow and the benefit justifies migration cost. Prefer additive high-level APIs, compatibility shims and explicit deprecations when they preserve clarity. Any intentional break must have:

1. a machine-readable ledger entry;
2. a documented replacement or a clear explanation when no replacement exists;
3. focused migration/regression tests;
4. an example or real-game workflow proving the replacement is usable;
5. release-note and upgrade-guide coverage before publication.

`Release/PyPI: frozen until SwirEngine 2.0`.
