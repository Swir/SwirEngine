from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.verify_2_1_release_candidate import check_release_candidate

ROOT = Path(__file__).resolve().parents[1]

ROADMAP = """# SwirEngine 2.1

Current verified progress: 10/10 milestones = 100.0%.

""" + "\n".join(f"- [x] **{index}. Milestone {index}.** Accepted." for index in range(1, 11))

README = """# SwirEngine

<!-- SWIR-PYPI-PROGRESS:START -->
```text
Scope: SwirEngine 2.1 - SwirEditor & Creator Workflow
Progress: [##############################] 100.0%
Counter: 10 / 10 milestones
Status: COMPLETE
```
<!-- SWIR-PYPI-PROGRESS:END -->

**Latest public stable release:** **SwirEngine 2.0.0**

```bash
python -m pip install -U "swirengine==2.0.0"
```
"""

WORKFLOW = """name: candidate
on:
  push:
    branches:
      - "release/**"
  workflow_dispatch:
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/verify_2_1_release_candidate.py
      - run: python tools/verify_2_1_release_readiness.py
      - run: python -m build
  matrix:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]
  release-evidence:
    steps:
      - run: python tools/release_evidence_2_1.py generate --require-windows-cp314
      - run: echo "SHA256SUMS release-provenance.json"
      - run: echo "swirengine-2.1.0-candidate-win-cp314"
"""

HISTORICAL_COMPATIBILITY_COMMANDS = (
    ("tools/verify_1_3_release_candidate.py", "--require-complete"),
    ("tools/verify_1_4_release_candidate.py", "--require-complete"),
    ("tools/verify_1_5_release_candidate.py", "--require-complete"),
    ("tools/verify_1_6_source_checkpoint.py", "--require-complete"),
    ("tools/verify_1_7_source_checkpoint.py", "--require-complete"),
    ("tools/verify_1_8_source_checkpoint.py", "--require-complete"),
    ("tools/verify_1_9_source_checkpoint.py", "--require-complete"),
)


def _write_candidate(root: Path) -> None:
    files = {
        "pyproject.toml": """[project]\nname = \"swirengine\"\nversion = \"2.1.0\"\nrequires-python = \">=3.10,<3.15\"\n""",
        "src/swirengine/__init__.py": '__version__ = "2.1.0"\n',
        "ROADMAP_2_1.md": ROADMAP,
        "README.md": README,
        "RELEASE_NOTES_2_1.md": (
            "Publication status: NOT PUBLISHED.\n"
            "The public stable release remains SwirEngine 2.0.0.\n"
        ),
        "docs/RELEASE_GATE_2_1.md": "Phase C publication decision remains separate.\n",
        ".github/workflows/release-candidate-2.1.yml": WORKFLOW,
        "tools/release_evidence_2_1.py": "# deterministic release evidence tool\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_release_candidate_contract_accepts_non_publishing_candidate(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    assert check_release_candidate(tmp_path) == []


@pytest.mark.parametrize("command", HISTORICAL_COMPATIBILITY_COMMANDS)
def test_release_candidate_preserves_locked_historical_contracts(command: tuple[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, *command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_release_candidate_contract_rejects_svg_inside_pypi_block(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        README.replace("Status: COMPLETE", 'Status: COMPLETE\n<img src="progress.svg" />'),
        encoding="utf-8",
    )

    errors = check_release_candidate(tmp_path)

    assert any("plain ASCII/text" in error for error in errors)


def test_release_candidate_contract_rejects_wrong_project_version(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace('version = "2.1.0"', 'version = "2.0.0"'),
        encoding="utf-8",
    )

    errors = check_release_candidate(tmp_path)

    assert any("version must be exactly 2.1.0" in error for error in errors)


def test_release_candidate_contract_rejects_runtime_version_drift(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    init_path = tmp_path / "src/swirengine/__init__.py"
    init_path.write_text('__version__ = "2.0.0"\n', encoding="utf-8")

    errors = check_release_candidate(tmp_path)

    assert any("runtime __version__ must be exactly 2.1.0" in error for error in errors)


def test_release_candidate_contract_rejects_pull_request_trigger(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    workflow = tmp_path / ".github/workflows/release-candidate-2.1.yml"
    workflow.write_text(WORKFLOW.replace("  push:\n", "  pull_request:\n  push:\n"), encoding="utf-8")

    errors = check_release_candidate(tmp_path)

    assert any("release-branch-scoped" in error for error in errors)


def test_release_candidate_contract_rejects_publish_capability(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    workflow = tmp_path / ".github/workflows/release-candidate-2.1.yml"
    workflow.write_text(WORKFLOW + "\n# pypa/gh-action-pypi-publish\n", encoding="utf-8")

    errors = check_release_candidate(tmp_path)

    assert any("non-publishing" in error for error in errors)


def test_release_candidate_contract_requires_exact_head_release_evidence(
    tmp_path: Path,
) -> None:
    _write_candidate(tmp_path)
    workflow = tmp_path / ".github/workflows/release-candidate-2.1.yml"
    workflow.write_text(
        WORKFLOW.replace("  release-evidence:\n", "  evidence-disabled:\n"),
        encoding="utf-8",
    )

    errors = check_release_candidate(tmp_path)

    assert any("release-evidence:" in error for error in errors)
