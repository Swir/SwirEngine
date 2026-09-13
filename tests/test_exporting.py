from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.exporting import ExportTarget, PackagingProfile, ProjectExporter


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "swirproject.toml").write_text('name = "Demo"\n', encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "sprite.txt").write_text("asset", encoding="utf-8")
    (root / "assets" / "__pycache__").mkdir()
    (root / "assets" / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
    return root


def test_profile_round_trip(tmp_path: Path) -> None:
    profile = PackagingProfile(
        name="release",
        target=ExportTarget.LINUX,
        app_name="Swir Demo",
        onefile=True,
        console=False,
        metadata={"channel": "stable"},
    )
    path = profile.save(tmp_path / "profile.json")

    assert PackagingProfile.load(path) == profile


def test_export_plan_is_deterministic_and_desktop_ready(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    profile = PackagingProfile(name="demo", target=ExportTarget.WINDOWS, onefile=True)
    exporter = ProjectExporter(root)

    plan = exporter.plan(profile, tmp_path / "out")

    assert [path.as_posix() for path in plan.files] == [
        "assets/sprite.txt",
        "main.py",
        "swirproject.toml",
    ]
    assert plan.experimental is False
    assert plan.native_build_command is not None
    assert "PyInstaller" in plan.native_build_command
    assert "--onefile" in plan.native_build_command


def test_export_copies_files_and_writes_manifest(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    profile = PackagingProfile(name="web-demo", target=ExportTarget.WEB)

    result = ProjectExporter(root).export(profile, tmp_path / "export")
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

    assert result.experimental is True
    assert result.native_build_command is None
    assert (result.output_dir / "main.py").is_file()
    assert (result.output_dir / "assets" / "sprite.txt").is_file()
    assert manifest["target"] == "web"
    assert manifest["experimental"] is True
    assert manifest["format"] == "swirengine-export"


def test_export_requires_existing_entrypoint(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    profile = PackagingProfile(name="broken", entrypoint="missing.py")

    with pytest.raises(FileNotFoundError, match="entrypoint"):
        ProjectExporter(root).plan(profile)


def test_profile_validation() -> None:
    with pytest.raises(ValueError, match="profile name"):
        PackagingProfile(name=" ")
    with pytest.raises(ValueError, match="entrypoint"):
        PackagingProfile(entrypoint=" ")
