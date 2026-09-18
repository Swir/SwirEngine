from __future__ import annotations

import tomllib
from pathlib import Path

from tools.verify_platform_matrix_2_0 import SUPPORTED_PYTHONS, SUPPORTED_SYSTEMS

ROOT = Path(__file__).resolve().parents[1]


def test_python_metadata_matches_candidate_2_0_range():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert {item.strip() for item in project["requires-python"].split(",")} == {
        ">=3.10",
        "<3.15",
    }
    classifiers = set(project["classifiers"])
    for minor in range(10, 15):
        assert f"Programming Language :: Python :: 3.{minor}" in classifiers
    assert project["version"] == "1.5.0"
    assert project["urls"]["Roadmap"].endswith("/ROADMAP_1_5.md")
    active_roadmap = (ROOT / "ROADMAP_2_0.md").read_text(encoding="utf-8")
    assert "# SwirEngine 2.0 Roadmap" in active_roadmap


def test_matrix_probe_scope_is_explicit_and_64_bit_only():
    assert SUPPORTED_SYSTEMS == {"Linux", "Windows", "Darwin"}
    assert SUPPORTED_PYTHONS == {"3.10", "3.11", "3.12", "3.13", "3.14"}
    source = (ROOT / "tools" / "verify_platform_matrix_2_0.py").read_text(encoding="utf-8")
    assert "pointer_bits != 64" in source
    assert "require_vendored_native" in source


def test_support_document_separates_os_python_from_architecture_and_shipping():
    document = (ROOT / "docs" / "SUPPORT_MATRIX_2_0.md").read_text(encoding="utf-8")
    for system in ("Windows", "Linux", "macOS"):
        assert system in document
    for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
        assert version in document
    assert "64-bit" in document
    assert "win_amd64" in document
    assert "32-bit Python is unsupported" in document
    assert "PyPy" in document
    assert "Milestone 7" in document
    assert "base engine" in document


def test_platform_matrix_workflow_covers_every_os_python_cell_and_clean_install():
    workflow = (ROOT / ".github" / "workflows" / "platform-matrix-2.0.yml").read_text(
        encoding="utf-8"
    )
    assert "ubuntu-24.04" in workflow
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow
    for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
        assert f'"{version}"' in workflow
    assert "verify_platform_matrix_2_0.py" in workflow
    assert "verify_clean_wheel_2_0.py" in workflow
    assert "build_vendored_wheel.py" in workflow
    assert "--require-vendored-native" in workflow

    clean_verifier = (ROOT / "tools" / "verify_clean_wheel_2_0.py").read_text(encoding="utf-8")
    assert "SWIR_GAME_DEMO_HEADLESS" in clean_verifier
    assert "examples/2d_game_demo/run_game.py" in clean_verifier
    assert "examples/3d_game_demo/run_game.py" in clean_verifier
