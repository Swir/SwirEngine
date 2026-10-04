from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.verify_2_2_1_release_candidate import (
    HISTORICAL_MANIFEST,
    IMMUTABLE_2_2_0_DIGESTS,
    MANIFEST,
    NEW_WORKFLOW_ENTRY,
    PACKAGE_DESCRIPTION,
    RELEASE_NOTES,
    REQUIRED_FILES,
    ROOT,
    WORKFLOW,
    check_release_candidate,
    validate_manifest_transition,
)


def _description() -> str:
    sections = [
        "Installation",
        "Quick start 2D",
        "Quick start 3D",
        "SwirEditor",
        "Multiplayer",
        "Rendering and tools",
        "Platform support",
        "Documentation",
    ]
    body = ["# SwirEngine 2.2.1", ""]
    for section in sections:
        body.extend(
            (
                f"## {section}",
                "",
                (
                    "SwirEngine provides complete 2D, 3D and multiplayer workflows through "
                    "a Python-first API and SwirEditor. This detailed section documents runtime, "
                    "creator tools, deterministic project data, verification boundaries and "
                    "production-oriented usage for 64-bit CPython installations. " * 2
                ),
                "",
            )
        )
    body.extend(
        (
            'python -m pip install -U "swirengine==2.2.1"',
            'python -m pip install -U "swirengine[audio]==2.2.1"',
            "Supported Python 3.10 through Python 3.14 on the documented 64-bit matrix.",
            "https://github.com/Swir/SwirEngine",
            "",
        )
    )
    return "\n".join(body)


def _workflow() -> str:
    sha = "a" * 40
    return f"""name: SwirEngine 2.2.1 Release Candidate
on:
  pull_request:
    branches: [main]
    paths:
      - pyproject.toml
      - src/**
      - PYPI_DESCRIPTION_2_2_1.md
      - RELEASE_NOTES_2_2_1.md
      - .github/release-gates/2.2.1-required-workflows.json
      - .github/workflows/release-candidate-2.2.1.yml
      - tools/**
      - tests/**
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{sha}
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
          fetch-depth: 0
          persist-credentials: false
      - run: test "${{{{ github.event.pull_request.head.ref }}}}" = "release/2.2.1"
      - run: python tools/verify_2_2_1_release_candidate.py
      - run: python tools/candidate_evidence_2_2_1.py verify
      - run: python tools/verify_clean_wheel_2_0.py --expected-version 2.2.1
      - run: python -m pytest
      - run: python -m ruff check .
      - run: python -m compileall tools tests src
      - run: python -m build && twine check dist/*
"""


def _pre_publication_readme() -> str:
    return (
        "# SwirEngine\n\n"
        "**Latest public stable release:** **SwirEngine 2.2.0**\n\n"
        'python -m pip install -U "swirengine==2.2.0"\n'
    )


def _candidate_root(tmp_path: Path) -> Path:
    root = tmp_path / "candidate"
    root.mkdir()
    for relative in REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    for relative in IMMUTABLE_2_2_0_DIGESTS:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "swirengine"\nversion = "2.2.1"\n'
        'readme = "PYPI_DESCRIPTION_2_2_1.md"\nrequires-python = ">=3.10,<3.15"\n',
        encoding="utf-8",
    )
    (root / "src/swirengine/__init__.py").write_text(
        '__version__ = "2.2.1"\n', encoding="utf-8"
    )
    (root / "README.md").write_text(_pre_publication_readme(), encoding="utf-8")
    shutil.copyfile(ROOT / "ROADMAP_2_2.md", root / "ROADMAP_2_2.md")
    (root / PACKAGE_DESCRIPTION).write_text(_description(), encoding="utf-8")
    (root / RELEASE_NOTES).write_text(
        "# SwirEngine 2.2.1 Release Notes\n\n"
        "This is a metadata-only maintenance release with no public API or runtime behavior "
        "changes. It publishes the expanded PYPI_DESCRIPTION_2_2_1.md package guide.\n",
        encoding="utf-8",
    )
    (root / WORKFLOW).write_text(_workflow(), encoding="utf-8")
    historical = json.loads((root / HISTORICAL_MANIFEST).read_text(encoding="utf-8"))
    patch = dict(historical)
    patch["required_workflows"] = [
        *historical["required_workflows"],
        NEW_WORKFLOW_ENTRY,
    ]
    (root / MANIFEST).write_text(json.dumps(patch), encoding="utf-8")
    return root


def test_complete_metadata_only_candidate_contract_passes(tmp_path: Path) -> None:
    root = _candidate_root(tmp_path)

    assert check_release_candidate(root) == []


def test_candidate_rejects_immutable_2_2_0_drift(tmp_path: Path) -> None:
    root = _candidate_root(tmp_path)
    (root / "PYPI_DESCRIPTION_2_2.md").write_text("changed\n", encoding="utf-8")

    errors = check_release_candidate(root)

    assert any("immutable 2.2.0 file changed" in error for error in errors)


def test_candidate_rejects_windows_normalized_marker_root(tmp_path: Path) -> None:
    root = _candidate_root(tmp_path)
    marker = root / ".release." / "publish-2.2.1 "
    marker.mkdir(parents=True)

    errors = check_release_candidate(root)

    assert any("publication control root" in error for error in errors)


def test_candidate_allows_historical_publication_marker_root(tmp_path: Path) -> None:
    root = _candidate_root(tmp_path)
    historical = root / ".release" / "publish-2.1.0"
    historical.mkdir(parents=True)
    (historical / "publication.json").write_text("{}\n", encoding="utf-8")

    assert check_release_candidate(root) == []


def test_manifest_rejects_reordering_or_replacement(tmp_path: Path) -> None:
    root = _candidate_root(tmp_path)
    payload = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    payload["required_workflows"][0], payload["required_workflows"][1] = (
        payload["required_workflows"][1],
        payload["required_workflows"][0],
    )
    (root / MANIFEST).write_text(json.dumps(payload), encoding="utf-8")

    errors = validate_manifest_transition(root)

    assert "2.2.1 manifest must preserve all historical entries in exact order" in errors


def test_description_rejects_relative_links(tmp_path: Path) -> None:
    root = _candidate_root(tmp_path)
    path = root / PACKAGE_DESCRIPTION
    path.write_text(path.read_text(encoding="utf-8") + "[bad](docs/local.md)\n", encoding="utf-8")

    errors = check_release_candidate(root)

    assert any("PyPI-safe absolute" in error for error in errors)
