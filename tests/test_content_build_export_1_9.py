from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.exporting import PackagingProfile, ProjectExporter


def _base_project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "main.py").write_text("print('game')\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "base.bin").write_bytes(b"base")
    return root


def test_export_stages_content_graph_files_outside_profile_include(tmp_path: Path) -> None:
    root = _base_project(tmp_path / "project")
    (root / "shipping").mkdir()
    (root / "shipping" / "world.bin").write_bytes(b"world")
    (root / "swirproject.toml").write_text(
        """
name = "Content Export"

[content]
include = ["assets"]

[[content.build.nodes]]
name = "shipping:world"
kind = "generated"
path = "shipping/world.bin"
load = "preload"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    files = {path.as_posix() for path in plan.files}
    assert "assets/base.bin" in files
    assert "shipping/world.bin" in files
    assert "swirproject.toml" in files


def test_export_rejects_missing_content_graph_file_before_staging(tmp_path: Path) -> None:
    root = _base_project(tmp_path / "project")
    (root / "swirproject.toml").write_text(
        """
name = "Content Export"

[content]
include = ["assets"]

[[content.build.nodes]]
name = "missing"
path = "shipping/missing.bin"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="content build export preflight failed"):
        ProjectExporter(root).plan(PackagingProfile(include=("assets",)))


def test_export_rejects_profile_that_excludes_required_content_graph_file(tmp_path: Path) -> None:
    root = _base_project(tmp_path / "project")
    (root / "shipping").mkdir()
    (root / "shipping" / "world.bin").write_bytes(b"world")
    (root / "swirproject.toml").write_text(
        """
name = "Content Export"

[content]
include = ["assets"]

[[content.build.nodes]]
name = "shipping:world"
path = "shipping/world.bin"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="excludes declared content build files"):
        ProjectExporter(root).plan(
            PackagingProfile(include=("assets",), exclude=("shipping",))
        )


def test_export_without_content_build_preserves_legacy_manifest_behavior(tmp_path: Path) -> None:
    root = _base_project(tmp_path / "project")
    (root / "swirproject.toml").write_text(
        '[legacy]\nformat = "pre-1.9"\n',
        encoding="utf-8",
    )

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    assert Path("assets/base.bin") in plan.files
    assert Path("swirproject.toml") in plan.files


def test_malformed_legacy_manifest_does_not_activate_content_build_preflight(
    tmp_path: Path,
) -> None:
    root = _base_project(tmp_path / "project")
    (root / "swirproject.toml").write_text(
        'this is not valid toml = "\n',
        encoding="utf-8",
    )

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    assert Path("assets/base.bin") in plan.files
    assert Path("swirproject.toml") in plan.files
