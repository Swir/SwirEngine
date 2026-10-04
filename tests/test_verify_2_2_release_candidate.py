from __future__ import annotations

import json
from pathlib import Path

from tools.verify_2_2_release_candidate import (
    MANIFEST,
    REQUIRED_WORKFLOW_PATHS,
    WORKFLOW,
    WORKFLOW_NAME,
    check_release_candidate,
    validate_candidate_workflow,
)


def _roadmap() -> str:
    milestones = [f"- [x] **{number}. Accepted milestone.**" for number in range(1, 10)]
    milestones.append("- [ ] **10. Production acceptance and 2.2 release readiness.**")
    return "\n".join(
        [
            "# SwirEngine 2.2 Roadmap",
            "",
            "Current verified progress: 9/10 milestones = 90.0%.",
            "",
            *milestones,
            "",
        ]
    )


def _workflow() -> str:
    paths = "\n".join(f'      - "{path}"' for path in REQUIRED_WORKFLOW_PATHS)
    return f"""name: {WORKFLOW_NAME}

on:
  pull_request:
    branches: [main]
    paths:
{paths}

permissions:
  contents: read

env:
  EXPECTED_SOURCE_SHA: ${{{{ github.event.pull_request.head.sha }}}}

jobs:
  candidate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
          persist-credentials: false
      - run: |
          test "${{{{ github.event.pull_request.head.ref }}}}" = "release/2.2.0-candidate"
          test "${{{{ github.event.pull_request.head.repo.full_name }}}}" = "${{{{ github.repository }}}}"
          test "${{{{ github.repository }}}}" = "Swir/SwirEngine"
          test "${{{{ github.event.pull_request.base.ref }}}}" = "main"
          test -f "$GITHUB_EVENT_PATH"
          test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"
      - run: python tools/verify_2_2_release_candidate.py
      - run: python tools/verify_2_2_release_readiness.py
      - run: python tools/verify_required_workflows_2_2.py
      - run: python tools/verify_distribution_audit_data_2_2.py --dist-dir dist --wheel-only
      - run: python tools/verify_clean_wheel_2_0.py --expected-version 2.2.0
      - run: |
          python tools/candidate_evidence_2_2.py generate --dist-dir dist --source-sha "$EXPECTED_SOURCE_SHA" --workflow-manifest .github/release-gates/2.2-required-workflows.json
          python tools/candidate_evidence_2_2.py verify --dist-dir dist --source-sha "$EXPECTED_SOURCE_SHA" --workflow-manifest .github/release-gates/2.2-required-workflows.json
      - uses: actions/upload-artifact@v4
        with:
          name: candidate-provenance.json
          path: dist/*
          retention-days: 7
  matrix:
    runs-on: ${{{{ matrix.os }}}}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]
    steps:
      - run: echo "matrix"
"""


def _manifest() -> str:
    workflows = [{"path": WORKFLOW, "name": WORKFLOW_NAME}]
    workflows.extend(
        {
            "path": f".github/workflows/required-{index:02d}.yml",
            "name": f"Required workflow {index:02d}",
        }
        for index in range(1, 47)
    )
    return json.dumps(
        {
            "schema_version": 1,
            "repository": "Swir/SwirEngine",
            "required_workflows": workflows,
        },
        indent=2,
    )


def _repository(tmp_path: Path) -> Path:
    files = {
        "pyproject.toml": """[project]
name = "swirengine"
version = "2.2.0"
readme = "PYPI_DESCRIPTION_2_2.md"
requires-python = ">=3.10,<3.15"
classifiers = [
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
]

[project.urls]
Roadmap = "https://github.com/Swir/SwirEngine/blob/main/ROADMAP_2_2.md"
"2.2 Roadmap" = "https://github.com/Swir/SwirEngine/blob/main/ROADMAP_2_2.md"
"2.1 Roadmap" = "https://github.com/Swir/SwirEngine/blob/main/ROADMAP_2_1.md"

[tool.hatch.build.targets.sdist]
exclude = ["/release-evidence", "/.release"]
""",
        "src/swirengine/__init__.py": '__version__ = "2.2.0"\n',
        "README.md": """# SwirEngine

SwirEngine 2.2.0 is the bound non-publishing candidate.
**Latest public stable release:** **SwirEngine 2.1.0**
```bash
python -m pip install -U "swirengine==2.1.0"
```
""",
        "ROADMAP_2_2.md": _roadmap(),
        "RELEASE_NOTES_2_2.md": """# SwirEngine 2.2.0 Release Notes

Artifacts use bound candidate provenance. Authoritative availability is established by the
immutable v2.2.0 tag and matching PyPI files.
""",
        "PYPI_DESCRIPTION_2_2.md": """# SwirEngine 2.2.0

Modern Python-first 2D/3D game engine with a unified API.
""",
        "docs/MIGRATING_TO_2_2.md": (
            "# Migration\n\nPhase B is a bound non-publishing candidate.\n"
        ),
        "docs/RELEASE_GATE_2_2.md": (
            "# Gate\n\n## Phase B — bound non-publishing candidate\n"
        ),
        WORKFLOW: _workflow(),
        MANIFEST: _manifest(),
        "tools/candidate_evidence_2_2.py": "# candidate evidence tool\n",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def test_complete_bound_non_publishing_candidate_contract_passes(tmp_path: Path) -> None:
    root = _repository(tmp_path)

    assert check_release_candidate(root) == []


def test_candidate_contract_rejects_version_disagreement(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    init_path = root / "src/swirengine/__init__.py"
    init_path.write_text('__version__ = "2.1.0"\n', encoding="utf-8")

    errors = check_release_candidate(root)

    assert any("runtime" in error for error in errors)


def test_candidate_contract_rejects_closing_roadmap_early(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    roadmap = root / "ROADMAP_2_2.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8")
        .replace("- [ ] **10.", "- [x] **10.")
        .replace("9/10 milestones = 90.0%", "10/10 milestones = 100.0%"),
        encoding="utf-8",
    )

    errors = check_release_candidate(root)

    assert any("9/10" in error for error in errors)


def test_candidate_contract_rejects_public_2_2_install_claim(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\npython -m pip install -U swirengine==2.2.0\n",
        encoding="utf-8",
    )

    errors = check_release_candidate(root)

    assert any("unpublished public install" in error for error in errors)


def test_candidate_contract_rejects_transient_distribution_text(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    description = root / "PYPI_DESCRIPTION_2_2.md"
    description.write_text(
        description.read_text(encoding="utf-8") + "\nNOT PUBLISHED candidate.\n",
        encoding="utf-8",
    )
    notes = root / "RELEASE_NOTES_2_2.md"
    notes.write_text(
        notes.read_text(encoding="utf-8") + "\nThe latest public stable release remains 2.1.0.\n",
        encoding="utf-8",
    )

    errors = check_release_candidate(root)

    assert any("transient repository status" in error for error in errors)
    assert any("transient candidate wording" in error for error in errors)


def test_candidate_contract_rejects_marker_windows_alias(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    marker = root / ".release" / "publish-2.2.0."
    marker.mkdir(parents=True)

    errors = check_release_candidate(root)

    assert any("Windows alias" in error for error in errors)


def test_candidate_workflow_rejects_publish_capability() -> None:
    broken = _workflow().replace('      - run: echo "matrix"', "      - run: twine upload dist/*")
    errors = validate_candidate_workflow(broken)

    assert any("forbidden publishing capability" in error for error in errors)


def test_candidate_contract_requires_candidate_workflow_in_manifest(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["required_workflows"][0] = {
        "path": ".github/workflows/release-readiness-2.2.yml",
        "name": "SwirEngine 2.2 Release Readiness",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = check_release_candidate(root)

    assert any("does not require the Phase B candidate workflow" in error for error in errors)


def test_candidate_contract_rejects_duplicate_manifest_path(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["required_workflows"][1]["path"] = manifest["required_workflows"][0]["path"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = check_release_candidate(root)

    assert any("duplicate paths" in error for error in errors)


def test_phase_e_fixture_is_not_reinterpreted_as_a_phase_b_candidate(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    roadmap = root / "ROADMAP_2_2.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8")
        .replace("- [ ] **10.", "- [x] **10.")
        .replace("9/10 milestones = 90.0%", "10/10 milestones = 100.0%"),
        encoding="utf-8",
    )
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        .replace("bound non-publishing candidate", "immutable public release")
        .replace("SwirEngine 2.1.0", "SwirEngine 2.2.0")
        .replace("swirengine==2.1.0", "swirengine==2.2.0"),
        encoding="utf-8",
    )
    (root / WORKFLOW).unlink()

    errors = check_release_candidate(root)

    assert errors
    assert any(
        "candidate workflow" in error
        or "missing required Phase B file" in error
        or "9/10" in error
        for error in errors
    )
