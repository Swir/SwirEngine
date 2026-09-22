from __future__ import annotations

from pathlib import Path

from tools.verify_2_1_release_candidate import check_release_candidate


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
"""


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
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_release_candidate_contract_accepts_non_publishing_candidate(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    assert check_release_candidate(tmp_path) == []


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


def test_release_candidate_contract_rejects_publish_capability(tmp_path: Path) -> None:
    _write_candidate(tmp_path)
    workflow = tmp_path / ".github/workflows/release-candidate-2.1.yml"
    workflow.write_text(WORKFLOW + "\n# pypa/gh-action-pypi-publish\n", encoding="utf-8")

    errors = check_release_candidate(tmp_path)

    assert any("must be non-publishing" in error for error in errors)
