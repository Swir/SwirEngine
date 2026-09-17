# SwirEngine 1.8 Source Checkpoint & Hardening

SwirEngine 1.8 is a **source-only** development checkpoint on the path to SwirEngine 2.0. It is not a public package version and must not create a `v1.8.0` tag, GitHub Release or package publication. The public package metadata remains frozen at **1.5.0** until the final 2.0 release policy is satisfied.

## Closeout objective

Milestone 10 closes the Render Graph & GPU Delivery roadmap only after the complete 1.8 stack is present, the authoritative roadmap reaches exactly 10/10 = 100.0%, all required compatibility/runtime/package gates are green on the exact candidate head, and a clean built wheel can exercise the representative source-only showcase.

The strict auditor is `tools/verify_1_8_source_checkpoint.py --require-complete`. Development mode intentionally accepts a coherent 9/10 candidate so the checkpoint infrastructure itself can be reviewed before Milestone 10 is marked complete. Strict mode must reject anything below 10/10.

## 1.8 systems under checkpoint

The checkpoint covers the complete additive 1.8 rendering scalability stack:

- Render Graph 3.0 planning (`render_graph18`)
- transient GPU resource pooling (`render_resources18`)
- staged texture uploads and logical residency (`render_uploads18`)
- material submission and pipeline-state caching (`render_submission18`)
- visibility and LOD submission (`visibility18`)
- non-blocking GPU timing capture (`render_timing18`)
- dynamic quality budgeting (`render_quality18`)
- Renderer2 compatibility bridge (`renderer2_bridge18`)
- bounded 2D/3D render showcase, soak and failure injection (`render_showcase18`)

All systems remain additive or opt-in. Stable 1.x public renderer behavior must remain unchanged when these systems are not explicitly used.

## Required compatibility gates

The exact final candidate must preserve the locked 1.4 and 1.5 contracts and the completed 1.6 and 1.7 source checkpoints. The 1.8 source-checkpoint workflow therefore runs the strict 1.7 auditor in addition to the 1.8 auditor, while the repository-wide pull-request workflows continue to cover the earlier hardening, demo and compatibility paths.

No failed required gate may be bypassed to close the roadmap.

## Python and source validation

The dedicated checkpoint validates source compatibility on **Python 3.10**, **Python 3.13** and **Python 3.14**. The matrix runs the 1.8 auditor, strict 1.7 compatibility audit, focused checkpoint/showcase tests and the source-only render showcase. Python 3.13 additionally runs full pytest, Ruff and compile validation.

The supported Python claim remains limited to environments actually represented by repository CI and packaging policy.

## Packaging and clean-install contract

The checkpoint builds both wheel and sdist with `python -m build`, validates metadata with `twine check`, creates a fresh virtual environment, installs the newly built wheel and verifies that:

1. the installed public package version remains `1.5.0`;
2. every 1.8 subsystem imports from the installed artifact rather than the repository checkout;
3. the source-only 2D/3D render showcase executes against the clean installation;
4. the package contains no requirement to publish an intermediate 1.8 artifact.

This is packaging validation only. It does not upload anything.

## Representative runtime evidence

Milestone 9 already supplies bounded 2D and 3D showcase workloads, long soak validation, transient-resource churn, duplicate-upload suppression, failure injection/recovery, Windows source execution and a real Linux Mesa OpenGL smoke path. Milestone 10 reuses that evidence as part of the closeout rather than inventing a documentation-only completion signal.

The game-demo and desktop-export workflows remain separate required repository gates and continue to guard real creator-facing paths.

## Completion rule

SwirEngine 1.8 may be marked complete only when:

- `ROADMAP_1_8.md` is exactly 10/10 = 100.0%;
- `tools/verify_1_8_source_checkpoint.py --require-complete` passes;
- Python 3.10, Python 3.13 and Python 3.14 checkpoint jobs pass;
- full tests, Ruff and compile validation pass;
- wheel/sdist build, metadata inspection and clean wheel install pass;
- the installed artifact imports the complete 1.8 stack and runs the source showcase;
- Windows and Linux source-showcase coverage passes;
- locked 1.4/1.5/1.6/1.7 contracts remain green;
- repository-wide runtime/demo/export gates on the exact final head are green.

After that verified source checkpoint, development continues toward 2.0. There is still **no intermediate 1.8 public release**.

**Release/PyPI remain frozen until SwirEngine 2.0.**
