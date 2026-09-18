from __future__ import annotations

import json
from pathlib import Path

from swirengine.cli import main, new_project
from swirengine.creator_workflow20 import CreatorProjectWorkflow


def test_new_project_is_creator_workflow_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("Creator2D", "2d")

    report = CreatorProjectWorkflow(root).inspect(
        profile_name="linux",
        platform="linux",
        environ={},
        home=tmp_path / "home",
    )

    assert report.ready
    assert report.mode == "2d"
    assert report.profiles == ("linux", "macos", "windows")
    assert report.selected_profile == "linux"
    assert report.run_plan_fingerprint is not None
    assert report.shipping_defaults_fingerprint is not None
    assert report.input_defaults_present
    assert report.settings_defaults_present
    assert report.editor_directories == ("scenes", "prefabs", "settings")
    assert report.diagnostics == ()
    assert len(report.fingerprint) == 64
    assert (root / "config" / "controls.json").is_file()
    assert (root / "config" / "settings.json").is_file()


def test_new_3d_project_uses_same_integrated_workflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("Creator3D", "3d")

    report = CreatorProjectWorkflow(root).inspect(
        platform="linux",
        environ={},
        home=tmp_path / "home",
    )

    assert report.ready
    assert report.mode == "3d"
    assert report.manifest_fingerprint
    assert report.run_plan_fingerprint


def test_workflow_prepare_is_idempotent_and_never_overwrites_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("PrepareSafe", "2d")
    controls = root / "config" / "controls.json"
    original = controls.read_text(encoding="utf-8")

    for relative in ("prefabs", "settings"):
        (root / relative).rmdir()
    (root / "config" / "settings.json").unlink()

    workflow = CreatorProjectWorkflow(root)
    created = {path.relative_to(root).as_posix() for path in workflow.prepare()}

    assert created == {"prefabs", "settings", "config/settings.json"}
    assert controls.read_text(encoding="utf-8") == original
    assert workflow.prepare() == ()


def test_missing_entrypoint_is_actionable_instead_of_raising(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("BrokenEntrypoint", "2d")
    (root / "main.py").unlink()

    report = CreatorProjectWorkflow(root).inspect(
        platform="linux",
        environ={},
        home=tmp_path / "home",
    )

    assert not report.ready
    errors = [item for item in report.diagnostics if item.severity == "error"]
    assert errors
    assert {item.code for item in errors} >= {"entrypoint-missing", "run-plan-invalid"}
    assert all(item.action for item in errors)


def test_invalid_scene_registry_becomes_creator_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("BrokenScenes", "2d")
    manifest = root / "swirproject.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + """
[scenes]
boot = "missing"

[scenes.registry.main]
path = "scenes/main.swirscene"
""",
        encoding="utf-8",
    )

    report = CreatorProjectWorkflow(root).inspect(
        platform="linux",
        environ={},
        home=tmp_path / "home",
    )

    assert not report.ready
    assert any(item.code == "scene-package-invalid" for item in report.diagnostics)


def test_missing_content_build_file_is_reported_with_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("BrokenContent", "2d")
    manifest = root / "swirproject.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + """
[[content.build.nodes]]
name = "asset:missing"
kind = "asset"
path = "assets/missing.bin"
load = "preload"
""",
        encoding="utf-8",
    )

    report = CreatorProjectWorkflow(root).inspect(
        platform="linux",
        environ={},
        home=tmp_path / "home",
    )

    assert not report.ready
    issue = next(
        item for item in report.diagnostics if item.code == "content-build-missing"
    )
    assert issue.path == "assets/missing.bin"
    assert issue.action


def test_workflow_json_cli_is_machine_readable(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("JsonWorkflow", "2d")

    return_code = main(["workflow", str(root), "--profile", "linux", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert return_code == 0
    assert payload["ready"] is True
    assert payload["name"] == "JsonWorkflow"
    assert payload["selected_profile"] == "linux"
    assert len(payload["fingerprint"]) == 64


def test_report_fingerprint_is_checkout_independent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first_parent = tmp_path / "first"
    second_parent = tmp_path / "second"
    first_parent.mkdir()
    second_parent.mkdir()

    monkeypatch.chdir(first_parent)
    first = new_project("PortableGame", "2d")
    monkeypatch.chdir(second_parent)
    second = new_project("PortableGame", "2d")

    first_report = CreatorProjectWorkflow(first).inspect(
        platform="linux",
        environ={},
        home=tmp_path / "home-a",
    )
    second_report = CreatorProjectWorkflow(second).inspect(
        platform="linux",
        environ={},
        home=tmp_path / "home-b",
    )

    assert first_report.ready and second_report.ready
    assert first_report.fingerprint == second_report.fingerprint
