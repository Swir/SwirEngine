from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.editor_build_export_frontend21 import (
    EditorBuildExportPanelController21,
    TkBuildExportEditorApp21,
    _parse_metadata_text,
)
from swirengine.editor_build_export_tooling21 import (
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
    (assets / "icon.png").write_bytes(b"test-icon\n")
    return root


def test_build_export_controller_exposes_exact_shipping_plan(tmp_path: Path) -> None:
    root = _project(tmp_path)
    tooling = EditorBuildExportTooling21(root, project_name="Neon Game")
    controller = EditorBuildExportPanelController21(tooling)

    frame = controller.preflight()

    assert frame.active_profile == "desktop"
    assert frame.target == "windows"
    assert frame.app_name == "Neon Game"
    assert frame.entrypoint == "main.py"
    assert frame.icon is None
    assert frame.metadata == ()
    assert frame.output_root == "dist"
    assert frame.planned_file_count == 3
    assert frame.native_build_planned
    assert not frame.experimental
    assert "3 files" in controller.status


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


def test_creator_configuration_round_trips_into_shipping_manifest(tmp_path: Path) -> None:
    root = _project(tmp_path)
    tooling = EditorBuildExportTooling21(root, project_name="Neon Game")
    controller = EditorBuildExportPanelController21(tooling)

    frame = controller.configure_active_profile(
        name="shipping",
        target=ExportTarget.LINUX,
        entrypoint="main.py",
        app_name="neon-game",
        icon="assets/icon.png",
        onefile=True,
        console=False,
        metadata={"channel": "preview", "build": "creator"},
    )
    saved = controller.save()

    assert frame.active_profile == "shipping"
    assert frame.profile_names == ("shipping",)
    assert frame.entrypoint == "main.py"
    assert frame.icon == "assets/icon.png"
    assert frame.metadata == (("build", "creator"), ("channel", "preview"))
    assert frame.onefile
    assert not frame.console
    assert frame.output_root == "dist"
    assert not saved.dirty

    reloaded = EditorBuildExportPanelController21(
        EditorBuildExportTooling21(root, project_name="Neon Game")
    )
    restored = reloaded.frame()
    assert restored.active_profile == "shipping"
    assert restored.icon == "assets/icon.png"
    assert restored.metadata == (("build", "creator"), ("channel", "preview"))
    assert restored.onefile
    assert not restored.console
    assert restored.output_root == "dist"

    artifact = reloaded.stage()
    payload = json.loads(Path(artifact.manifest).read_text(encoding="utf-8"))
    assert artifact.checksums_verified
    assert "assets/icon.png" in payload["files"]
    assert payload["metadata"] == {"channel": "preview", "build": "creator"}


def test_creator_configuration_rejects_invalid_icon_without_mutating_profile(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    tooling = EditorBuildExportTooling21(root, project_name="Neon Game")
    controller = EditorBuildExportPanelController21(tooling)
    before = tooling.snapshot()

    with pytest.raises(FileNotFoundError):
        controller.configure_active_profile(
            name="shipping",
            target=ExportTarget.LINUX,
            entrypoint="main.py",
            app_name="neon-game",
            icon="assets/missing.png",
            onefile=False,
            console=True,
            metadata={},
        )

    after = tooling.snapshot()
    assert after.config == before.config
    assert after.dirty == before.dirty


def test_creator_metadata_parser_is_strict_and_deterministic() -> None:
    assert _parse_metadata_text("") == {}
    assert _parse_metadata_text('{"channel": "preview", "build": "creator"}') == {
        "channel": "preview",
        "build": "creator",
    }
    with pytest.raises(EditorBuildExportToolingError, match="JSON object"):
        _parse_metadata_text('["preview"]')
    with pytest.raises(EditorBuildExportToolingError, match="keys and values"):
        _parse_metadata_text('{"build": 21}')


def test_stage_artifact_inspection_detects_checksum_regression(tmp_path: Path) -> None:
    root = _project(tmp_path)
    controller = EditorBuildExportPanelController21(
        EditorBuildExportTooling21(root, project_name="NeonGame")
    )

    report = controller.stage()

    assert report.file_count == 3
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
