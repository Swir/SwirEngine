# SwirEngine 1.6 Source Checkpoint Hardening

SwirEngine 1.6 is an internal source-development checkpoint on the path from the published 1.5.0 baseline to SwirEngine 2.0. It is deliberately **not** a public package release.

**Release/PyPI: frozen until SwirEngine 2.0**

The purpose of this gate is to prove that the complete 1.6 source line can be carried forward safely without changing the public distribution version or weakening the stable 1.x compatibility contract.

## Publication freeze

The following rules are part of the checkpoint contract:

- `v1.5.0` remains the latest public GitHub/PyPI release while 1.6 is developed.
- `pyproject.toml` and `swirengine.__version__` remain `1.5.0` during the source-only 1.6 checkpoint.
- no `v1.6.0` tag, GitHub Release, PyPI upload, Trusted Publishing job, or dedicated 1.6 publication workflow is created;
- finishing 1.6 means recording a verified source checkpoint and moving development forward, not publishing a package;
- the next public GitHub Release and PyPI publication are reserved for SwirEngine 2.0 after its own verified 10/10 gate.

## Checkpoint auditor

Run the development audit at any point in the 1.6 line:

```bash
python tools/verify_1_6_source_checkpoint.py
```

The development mode verifies the frozen package/runtime version, 1.6 milestone surfaces, locked compatibility auditors, hardening workflow, release-freeze policy, and absence of a dedicated 1.6 tag/publication workflow.

The final source checkpoint additionally requires the roadmap itself to be exactly 10/10:

```bash
python tools/verify_1_6_source_checkpoint.py --require-complete
```

The strict command is intentionally unsuitable for a 9/10 branch. The CI workflow switches to strict mode only when `ROADMAP_1_6.md` advertises the final `100.0%` / `10/10` state.

## Required validation

The exact final checkpoint head must satisfy all of these groups.

### 1. Compatibility and source contracts

- full test suite on the primary validation runtime;
- focused 1.6 contracts on Python 3.10, 3.13 and 3.14;
- locked 1.3, 1.4 and 1.5 contract auditors;
- stable networking/multiplayer regression coverage;
- strict Ruff and compile checks for source, tests, examples and tools.

### 2. All 1.6 deterministic workload gates

The checkpoint reruns every milestone workload on one coherent head:

```text
benchmark_multiplayer_replication_1_6.py
benchmark_prediction_reconciliation_1_6.py
benchmark_session_lifecycle_1_6.py
benchmark_transport_qos_1_6.py
benchmark_dedicated_server_1_6.py
benchmark_content_delivery_1_6.py
benchmark_platform_services_1_6.py
benchmark_network_profiler_1_6.py
benchmark_multiplayer_showcase_1_6.py
```

These are regression/workload contracts, not FPS claims.

### 3. Source showcase and runtime smoke

- run every creator-facing 1.6 example;
- run the source-only multiplayer showcase and deterministic soak workload;
- run both SwirEngine 2D Game Demo and SwirEngine 3D Game Demo in headless mode;
- retain the existing dedicated Linux/Windows showcase workflows as independent platform evidence.

### 4. Distribution reproducibility without publication

The checkpoint still builds the package so future source stages start from a known-good distribution boundary:

```bash
python -m build
python -m twine check dist/*
```

A fresh virtual environment then installs the locally built wheel, checks that the installed version remains `1.5.0`, imports every new 1.6 module, and runs representative source-only demos against the clean installation. The generated wheel/sdist are CI artifacts only; they are not uploaded to PyPI or attached to a GitHub Release.

## Finalization rule

Milestone 10 may be checked only after the exact final candidate head passes the source-checkpoint workflow and the repository-wide compatibility gates. Once merged, `ROADMAP_1_6.md` may state 10/10 and development can continue to the next source stage toward 2.0.

Do not reinterpret a green 1.6 checkpoint as permission to publish 1.6. The public release boundary remains SwirEngine 2.0.
