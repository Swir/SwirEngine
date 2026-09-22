from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.editor_build_export_tooling21 import (
    BuildExportConfig21,
    EditorBuildExportTooling21,
    EditorBuildExportToolingError,
)
from swirengine.exporting import ExportTarget, PackagingProfile


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "hero.txt").write_text("hero\n", encoding="utf-8")
    return root


def test_default_wizard_preflight_uses_shipping_exporter(tmp_path: Path) -> None:
    root = _project(tmp_path)
    wizard = EditorBuildExportTooling21(root, project_name="Neon Game")

    plan = wizard.preflight()

    assert plan.project_root == root.resolve()
    assert plan.profile.name == "desktop"
    assert plan.profile.app_name == "Neon Game"
    assert plan.target is ExportTarget.WINDOWS
    assert Path("main.py") in plan.files
    assert Path("assets/hero.txt") in plan.files
    assert plan.output_dir == root.resolve() / "dist" / "Neon Game-windows"
    assert not wizard.dirty


def test_profile_authoring_is_deterministic_and_persistent(tmp_path: Path) -> None:
    root = _project(tmp_path)
    wizard = EditorBuildExportTooling21(root, project_name="Neon Game")
    linux = PackagingProfile(
        name="linux-ci",
        target=ExportTarget.LINUX,
        app_name="neon-game",
        include=("assets",),
        onefile=True,
        console=False,
        metadata={"channel": "preview"},
    )

    wizard.upsert_profile(linux)
    wizard.select_profile("linux-ci")
    wizard.set_output_root("artifacts/export")
    assert wizard.dirty
    saved = wizard.save()
    first = wizard.target.read_text(encoding="utf-8")

    reloaded = EditorBuildExportTooling21(root, project_name="ignored")
    assert not reloaded.dirty
    assert reloaded.config == saved.config
    assert reloaded.config.active.target is ExportTarget.LINUX
    assert reloaded.output_dir() == root.resolve() / "artifacts/export/neon-game-linux"
    assert reloaded.target.read_text(encoding="utf-8") == first
    payload = json.loads(first)
    assert payload["format"] == "swirengine.build-export"
    assert payload["format_version"] == 1


def test_stage_produces_runtime_manifest_and_checksums(tmp_path: Path) -> None:
    root = _project(tmp_path)
    wizard = EditorBuildExportTooling21(root, project_name="NeonGame")

    result = wizard.stage()

    assert result.output_dir == root.resolve() / "dist/NeonGame-windows"
    assert result.manifest.is_file()
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["format"] == "swirengine-export"
    assert manifest["target"] == "windows"
    assert manifest["app_name"] == "NeonGame"
    assert "main.py" in manifest["files"]
    assert "assets/hero.txt" in manifest["files"]
    assert set(manifest["files"]) <= set(manifest["sha256"])
    assert (result.output_dir / "swirengine-build.spec").is_file()


def test_invalid_output_root_and_profile_configuration_are_rejected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    wizard = EditorBuildExportTooling21(root)

    with pytest.raises(EditorBuildExportToolingError, match="project-relative"):
        wizard.set_output_root("../outside")
    with pytest.raises(EditorBuildExportToolingError, match="last export profile"):
        wizard.remove_profile("desktop")
    with pytest.raises(EditorBuildExportToolingError, match="active export profile"):
        BuildExportConfig21(
            active_profile="missing",
            output_root="dist",
            profiles=(PackagingProfile(name="desktop"),),
        )
