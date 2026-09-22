from __future__ import annotations

from pathlib import Path

from swirengine.editor_build_export_frontend21 import (
    EditorBuildExportPanelController21,
    TkBuildExportEditorApp21,
)
from swirengine.editor_build_export_tooling21 import EditorBuildExportTooling21
from swirengine.exporting import ExportTarget, PackagingProfile


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "hero.txt").write_text("hero\n", encoding="utf-8")
    return root


def test_build_export_controller_exposes_exact_shipping_plan(tmp_path: Path) -> None:
    root = _project(tmp_path)
    tooling = EditorBuildExportTooling21(root, project_name="Neon Game")
    controller = EditorBuildExportPanelController21(tooling)

    frame = controller.preflight()

    assert frame.active_profile == "desktop"
    assert frame.target == "windows"
    assert frame.app_name == "Neon Game"
    assert frame.planned_file_count == 2
    assert frame.native_build_planned
    assert not frame.experimental
    assert "2 files" in controller.status


def test_build_export_controller_authors_profiles_and_preserves_runtime_fields(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    tooling = EditorBuildExportTooling21(root, project_name="Neon Game")
    controller = EditorBuildExportPanelController21(tooling)
    profile = PackagingProfile(
        name="linux-preview",
        target=ExportTarget.LINUX,
        entrypoint="main.py",
        app_name="neon-game",
        include=("assets",),
        icon="assets/icon.png",
        onefile=True,
        console=False,
        metadata={"channel": "preview"},
    )

    frame = controller.upsert_profile(profile)
    controller.set_output_root("artifacts/export")

    assert frame.active_profile == "linux-preview"
    assert tooling.config.active.icon == "assets/icon.png"
    assert tooling.config.active.onefile
    assert not tooling.config.active.console
    assert tooling.config.active.metadata == {"channel": "preview"}
    assert tooling.dirty


def test_stage_artifact_inspection_detects_checksum_regression(tmp_path: Path) -> None:
    root = _project(tmp_path)
    controller = EditorBuildExportPanelController21(
        EditorBuildExportTooling21(root, project_name="NeonGame")
    )

    report = controller.stage()

    assert report.file_count == 2
    assert report.total_bytes > 0
    assert report.checksums_verified
    assert report.missing_files == ()
    assert report.mismatched_files == ()
    assert report.native_spec is not None

    staged_main = Path(report.output_dir) / "main.py"
    staged_main.write_text("print('tampered')\n", encoding="utf-8")

    damaged = controller.inspect_staged()

    assert not damaged.checksums_verified
    assert damaged.mismatched_files == ("main.py",)
    assert "integrity problems" in controller.status


def test_integrated_editor_shell_includes_build_export_wizard() -> None:
    from swirengine.editor_asset_app21 import TkIntegratedEditorApp21

    assert issubclass(TkIntegratedEditorApp21, TkBuildExportEditorApp21)
