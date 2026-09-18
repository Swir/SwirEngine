<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.0 Roadmap — Complete Game Production & Public Release

SwirEngine 1.9 is the completed source-only production checkpoint. SwirEngine 2.0 is the next public
release line and must turn that accumulated runtime/tooling work into a stable, documented, reproducible
creator product for complete 2D, 3D and multiplayer games.

**Current verified progress: 0/10 milestones = 0.0%.**

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.0 verified roadmap progress: 0 of 10 milestones, 0.0%, in progress" />

**Verified active scope:** 0/10 milestones = 0.0% — IN PROGRESS.  
**Release readiness:** NOT READY. The public package remains SwirEngine 1.5.0 until this roadmap reaches verified 10/10 and the final 2.0 release gate passes.

A milestone is checked only after implementation, integration, focused tests, creator-facing evidence,
its dedicated gate and all required compatibility/runtime/packaging regressions pass on the exact final head.
Cosmetic work, documentation-only changes and existence of a subsystem do not raise this percentage by themselves.

## Release policy

- Published `v1.4.0` and `v1.5.0` remain immutable historical releases except for genuine maintenance fixes.
- Source checkpoints 1.6–1.9 stay source-only and must not receive retroactive tags, GitHub Releases or PyPI packages.
- `swirengine.__version__` and `[project].version` remain `1.5.0` during normal 2.0 source development.
- The version changes to `2.0.0` only in the final release-candidate path after the roadmap reaches its verified completion criteria.
- The next public GitHub Release and PyPI publication is SwirEngine 2.0 only.
- Public 2.0 publication requires the complete platform/Python/runtime/packaging/real-game gate and a clean public-index install verification.

## Milestones

- [ ] **1. Public API Freeze & 1.x Migration Contract**
  - immutable machine-readable snapshot of the released 1.5.0 root public API;
  - explicit 1.5.0 → 2.0.0 migration ledger for graduated exports and intentional removals;
  - deterministic static verifier for API drift, replacements and version-state rules;
  - documented migration policy that favors additive creator-facing APIs and explicit compatibility shims;
  - Python 3.10/3.13/3.14 gate plus the completed 1.9 checkpoint and repository regressions.

- [ ] **2. Creator Project & Editor Workflow**
  - one coherent new/open/edit/run/debug/export workflow for real projects;
  - scene hierarchy, inspector, asset browser, preview/play isolation and undo/redo integrated into that flow;
  - actionable diagnostics for broken projects/assets instead of silent partial state;
  - representative 2D and 3D projects editable without hand-editing engine internals.

- [ ] **3. Asset, Scene & Prefab Authoring Delivery**
  - creator-friendly import/reimport path with deterministic source/derived asset identity;
  - scene/prefab authoring, validation and dependency visibility connected to the 1.9 shipping graph;
  - bounded cache/streaming behavior and clear missing/corrupt asset diagnostics;
  - real-game integration proving author → edit → package → reload behavior.

- [ ] **4. Integrated Gameplay Production Stack**
  - animation, physics/collision, navigation/AI, audio, input, UI and save/profile systems proven together;
  - high-level defaults for common game patterns without removing lower-level control;
  - deterministic lifecycle/cleanup behavior across scene transitions and restart/load flows;
  - complete gameplay fixture exercising the stack rather than isolated subsystem demos.

- [ ] **5. Renderer Scalability & Reproducible Performance Evidence**
  - measured 2D/3D renderer workloads for draw submission, visibility, instancing, streaming and frame diagnostics;
  - regression ceilings based on reproducible workloads instead of unsupported FPS claims;
  - honest feature/performance comparison notes only where equivalent scenarios can be reproduced;
  - representative visual scenes that expose renderer bottlenecks before release.

- [ ] **6. Multiplayer & Dedicated Server Shipping**
  - production client/server lifecycle with explicit protocol/version compatibility;
  - dedicated/headless server packaging and documented deployment path;
  - reconnect, timeout, late-join, session teardown and adverse-network behavior;
  - deterministic multiplayer fixture plus bounded soak/failure validation.

- [ ] **7. Reliability, Resource Lifetime & Failure Recovery Audit**
  - architecture/public-API consistency audit across runtime and creator systems;
  - resource ownership and repeated load/unload/restart validation for CPU/GPU/audio/network state;
  - crash/failure injection covering corrupt content, unavailable devices and partial I/O;
  - no known critical/high-severity or release-blocking issues left unresolved.

- [ ] **8. Supported Python, Platform, Packaging & Export Matrix**
  - exact supported Python/OS matrix based only on green CI/runtime evidence;
  - wheel/sdist metadata and clean-install validation outside the repository;
  - native Windows/Linux/macOS export/build/runtime verification where support is claimed;
  - unsupported cross-compilation/experimental targets documented without marketing them as stable.

- [ ] **9. Representative Games & Creator Usability Gate**
  - polished source-only 2D, 3D and multiplayer projects built through the documented creator workflow;
  - title/settings/input/save/scenes/assets/gameplay/export/runtime all exercised end to end;
  - fresh-machine/clean-environment reproduction of documented setup and shipping steps;
  - docs and examples corrected whenever the real-game gate exposes awkward or missing workflows.

- [ ] **10. 2.0 Release-Candidate Final Gate**
  - final migration/API audit and exact package version transition to `2.0.0`;
  - full supported CI/runtime/packaging/export/real-game matrix green on the exact release candidate;
  - wheel/sdist/native artifact integrity, reproducibility metadata and release notes verified;
  - README/docs/upgrade guide accurately match the shipping product and limitations;
  - only after this milestone reaches verified completion may the repository publish the 2.0 GitHub Release and PyPI package, followed by public-index clean-install verification.

## Milestone 1 verification contract

Milestone 1 is complete only when the exact final implementation candidate satisfies all of the following:

1. `docs/api-contracts/swirengine-1.5-public-api.json` is pinned to released `v1.5.0`, contains the complete ordered root `swirengine.__all__` baseline and validates its own count/hash.
2. The released baseline is never rewritten merely to make source changes pass; 2.0 differences live only in the separate migration ledger.
3. `docs/api-contracts/swirengine-2.0-migration.json` explicitly lists every newly graduated root export and every intentional baseline removal, with migration rationale and a real public replacement where one is declared.
4. The verifier rejects undocumented baseline removals, undocumented root additions, stale ledger entries, duplicate names, invalid replacements and corrupted baseline metadata.
5. The verifier parses `src/swirengine/__init__.py` statically and rejects unbound `__all__` names without importing renderer/audio/network/editor backends as a side effect.
6. Normal source development requires both `swirengine.__version__` and `[project].version` to remain `1.5.0`, preserving the no-intermediate-release policy.
7. Explicit release-candidate mode requires both version surfaces to be exactly `2.0.0`; it cannot silently accept a mixed or premature package version.
8. `docs/API_MIGRATION_2_0.md` documents how creators migrate and establishes that source-only systems are not automatically public just because they exist in the repository.
9. Focused tests prove baseline integrity, undeclared-add/remove rejection, explicit graduation/removal behavior, replacement validation and release-candidate version rules.
10. The dedicated Python 3.10/3.13/3.14 API gate, strict completed 1.9 checkpoint, progress-SVG check, Ruff and compile pass, followed by all triggered repository compatibility/runtime/packaging gates before this checkbox is marked complete.

`Release/PyPI: frozen until SwirEngine 2.0`.
