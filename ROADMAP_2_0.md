<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.0 Roadmap — Release-Quality Python-First Game Production

**Historical verified progress: 10/10 milestones = 100.0%.**

**Release state:** SwirEngine **2.0.0 is published** on GitHub and PyPI. The immutable `v2.0.0` source is commit `4c219f3bed4c107c612a58fa2fb1f1362b4dfc46`.

This roadmap is now a **completed historical release scope**. Active quality work continues in [`POST_RELEASE_AUDIT_2_0.md`](POST_RELEASE_AUDIT_2_0.md), which owns the live `assets/readme/progress-mini.svg` presentation. The exact pre-publication roadmap, milestone contracts and detailed evidence are permanently preserved at the immutable [`v2.0.0` roadmap snapshot](https://github.com/Swir/SwirEngine/blob/v2.0.0/ROADMAP_2_0.md).

Source-only 1.6–1.9 checkpoints remain historical engineering evidence and were not retroactively published.

## Release gate principles preserved from the completed scope

- Preserve the stable 1.x compatibility floor unless a deliberate 2.0 migration is documented, tested and justified.
- Prefer creator-facing end-to-end workflows over disconnected subsystem demos.
- Keep representative 2D, 3D and multiplayer games as integration fixtures, not separate releases.
- Require reproducible evidence for performance or competitive comparisons; do not make unsupported superiority claims.
- Validate shipping on each claimed host platform and keep unsupported combinations explicit.
- Keep roadmap completion, public-release verification and post-release audit status as separate claims.
- Keep published release history immutable.

## Completed milestones

- [x] **1. Public API & Migration Contract** — machine-verifiable compatibility floor from the published `v1.5.0` root API plus explicit migration/API-stability evidence.
- [x] **2. Creator Workflow & Integrated Tooling** — coherent project validation/preparation/run/scene/content/settings/save/export workflow with actionable diagnostics.
- [x] **3. Multiplayer & Dedicated Server Production Contract** — deterministic compatibility, replication/session lifecycle, reconnect/resync and headless fixed-tick server integration.
- [x] **4. Renderer, Runtime Scalability & Resource Lifecycle** — bounded streaming/cache/resource behavior and representative production-sized 2D/3D workload verification.
- [x] **5. Final Python & Platform Support Matrix** — verified 64-bit CPython 3.10–3.14 base-engine matrix across hosted Windows, Linux and macOS runners, with explicit non-claims.
- [x] **6. Representative Real-Game Shipping Gate** — maintained 2D, 3D and multiplayer fixtures driven through creator, runtime, staged export, data-boundary and failure-path checks.
- [x] **7. Packaging, Clean Install & Native Desktop Shipping** — exact-source wheel/sdist validation, isolated installs and host-native packaged-game execution on claimed platforms.
- [x] **8. Performance Evidence & Competitive Quality Audit** — deterministic regression workloads with reproducible context and no unsupported cross-engine performance claims.
- [x] **9. Export/Build Integrity, Diagnostics & Release Safety** — deterministic build identity/inventory integrity plus bounded, redacted support-bundle and release-safety verification.
- [x] **10. SwirEngine 2.0 Final Release Gate & Public Verification** — complete exact-head finalization, immutable tag, Trusted Publishing, GitHub Release and fresh public PyPI install verification.

## Verified release evidence

| Evidence | Verified result |
|---|---|
| Completed release roadmap | `10/10 = 100.0%` |
| Immutable tag | `v2.0.0` |
| Release source | `4c219f3bed4c107c612a58fa2fb1f1362b4dfc46` |
| GitHub Release | Published 2026-09-19 |
| PyPI | `swirengine==2.0.0` public |
| Public-install verification | Ubuntu/Python 3.13, macOS/Python 3.13, Windows/Python 3.14 |
| Historical 1.6–1.9 policy | Source-only; not published |

The release workflow rebuilt the exact immutable tag, re-ran the final compatibility, runtime, real-game, performance, packaging and release-safety contracts, published through the registered PyPI Trusted Publisher identity, created the GitHub Release, and verified installation from the public PyPI Simple index. The first Ubuntu public-install attempt encountered a short Simple-index propagation delay after publication; an unchanged rerun succeeded. That incident is preserved as a post-release hardening target rather than hidden or reclassified as application progress.

## Historical verification sources

The full milestone-by-milestone contracts and implementation evidence remain available from the immutable release snapshot:

- [`ROADMAP_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/ROADMAP_2_0.md)
- [`RELEASE_NOTES_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/RELEASE_NOTES_2_0.md)
- [`docs/RELEASE_GATE_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/docs/RELEASE_GATE_2_0.md)
- [`docs/RELEASE_SAFETY_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/docs/RELEASE_SAFETY_2_0.md)
- [`docs/PACKAGING_SHIPPING_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/docs/PACKAGING_SHIPPING_2_0.md)
- [`docs/REAL_GAME_SHIPPING_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/docs/REAL_GAME_SHIPPING_2_0.md)
- [`docs/SUPPORT_MATRIX_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/docs/SUPPORT_MATRIX_2_0.md)
- [`docs/MIGRATING_TO_2_0.md` at `v2.0.0`](https://github.com/Swir/SwirEngine/blob/v2.0.0/docs/MIGRATING_TO_2_0.md)

## Active scope

Continue with [`POST_RELEASE_AUDIT_2_0.md`](POST_RELEASE_AUDIT_2_0.md). Its progress is intentionally independent of this completed historical 10/10 release roadmap and cannot be raised by cosmetic documentation work alone.
