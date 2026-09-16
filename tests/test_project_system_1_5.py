from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import swirengine.cli as cli
from swirengine.project import (
    PROJECT_SCHEMA_VERSION,
    ProjectConfigError,
    discover_project,
    load_project_manifest,
)


def _write_manifest(root: Path, body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "swirproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_new_project_round_trips_manifest_and_doctor(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    root = cli.new_project('Quoted "Project"', "3d")

    manifest = load_project_manifest(root)
    assert manifest.schema == PROJECT_SCHEMA_VERSION
    assert manifest.name == 'Quoted "Project"'
    assert manifest.mode == "3d"
    assert manifest.entrypoint == Path("main.py")
    assert manifest.assets_dir == Path("assets")
    assert manifest.layout_ok

    assert cli.main(["doctor", str(root)]) == 0
    captured = capsys.readouterr()
    assert "Project status: OK" in captured.out
    assert "mode=3d" in captured.out


def test_legacy_minimal_manifest_keeps_1x_defaults(tmp_path):
    root = tmp_path / "legacy"
    _write_manifest(
        root,
        'name = "Legacy"\nmode = "2d"\nengine = ">=1.0,<2.0"\n',
    )

    manifest = load_project_manifest(root)
    assert manifest.schema == 1
    assert manifest.entrypoint == Path("main.py")
    assert manifest.assets_dir == Path("assets")
    assert manifest.scenes_dir == Path("scenes")
    assert manifest.scripts_dir == Path("scripts")


def test_discover_project_walks_up_from_nested_path(tmp_path):
    root = tmp_path / "game"
    _write_manifest(root, 'name = "Nested"\nmode = "2d"\nengine = ">=1.0,<2.0"\n')
    nested = root / "scripts" / "gameplay"
    nested.mkdir(parents=True)

    manifest = discover_project(nested)
    assert manifest.root == root.resolve()
    assert manifest.name == "Nested"


def test_windows_relative_separators_are_normalized_portably(tmp_path):
    root = tmp_path / "portable"
    _write_manifest(
        root,
        "\n".join(
            (
                'name = "Portable"',
                'mode = "2d"',
                'engine = ">=1.0,<2.0"',
                'entrypoint = "scripts\\\\start.py"',
            )
        ),
    )

    manifest = load_project_manifest(root)
    assert manifest.entrypoint == Path("scripts") / "start.py"
    assert manifest.entrypoint.as_posix() == "scripts/start.py"


@pytest.mark.parametrize(
    "unsafe",
    (
        "../outside.py",
        "/tmp/outside.py",
        "C:/outside/main.py",
        r"C:\outside\main.py",
        r"\\server\share\main.py",
    ),
)
def test_manifest_rejects_non_portable_or_escaping_entrypoints(tmp_path, unsafe):
    root = tmp_path / "unsafe"
    _write_manifest(
        root,
        "\n".join(
            (
                'name = "Unsafe"',
                'mode = "2d"',
                'engine = ">=1.0,<2.0"',
                f"entrypoint = {json.dumps(unsafe)}",
            )
        ),
    )

    with pytest.raises(ProjectConfigError, match="entrypoint"):
        load_project_manifest(root)


def test_manifest_rejects_unknown_schema_and_mode(tmp_path):
    root = tmp_path / "invalid"
    _write_manifest(root, 'schema = 2\nname = "Bad"\nmode = "vr"\nengine = "1.x"\n')
    with pytest.raises(ProjectConfigError, match="unsupported project schema"):
        load_project_manifest(root)

    (root / "swirproject.toml").write_text(
        'schema = 1\nname = "Bad"\nmode = "vr"\nengine = "1.x"\n', encoding="utf-8"
    )
    with pytest.raises(ProjectConfigError, match="mode must be one of"):
        load_project_manifest(root)


def test_diagnostics_report_incomplete_layout(tmp_path):
    root = tmp_path / "broken"
    _write_manifest(root, 'name = "Broken"\nmode = "2d"\nengine = "1.x"\n')
    manifest = load_project_manifest(root)

    by_code = {item.code: item for item in manifest.diagnostics()}
    assert by_code["manifest"].ok
    assert not by_code["entrypoint"].ok
    assert not by_code["assets"].ok
    assert not manifest.layout_ok


def test_export_uses_manifest_defaults_and_content_paths(tmp_path, monkeypatch, capsys):
    root = tmp_path / "game"
    _write_manifest(
        root,
        "\n".join(
            (
                'schema = 1',
                'name = "Manifest Name"',
                'mode = "2d"',
                'engine = ">=1.0,<2.0"',
                'entrypoint = "scripts/start.py"',
                "",
                "[paths]",
                'assets = "content"',
                'scenes = "worlds"',
                'scripts = "scripts"',
            )
        ),
    )
    (root / "scripts").mkdir()
    (root / "scripts" / "start.py").write_text("print('ok')\n", encoding="utf-8")

    captured_profile = {}

    class FakeExporter:
        def __init__(self, project):
            assert Path(project) == root.resolve()

        def export(self, profile, output):
            captured_profile["value"] = profile
            return SimpleNamespace(
                output_dir=root / "dist",
                experimental=False,
                native_build_command=None,
            )

    monkeypatch.setattr(cli, "ProjectExporter", FakeExporter)
    assert cli.main(["export", str(root), "--target", "windows"]) == 0
    profile = captured_profile["value"]
    assert profile.name == "Manifest Name"
    assert profile.entrypoint == "scripts/start.py"
    assert profile.include == ("content", "worlds", "scripts")
    assert "Exported windows" in capsys.readouterr().out


def test_doctor_returns_nonzero_for_missing_project_layout(tmp_path, capsys):
    root = tmp_path / "broken"
    _write_manifest(root, 'name = "Broken"\nmode = "2d"\nengine = "1.x"\n')

    assert cli.main(["doctor", str(root)]) == 2
    captured = capsys.readouterr()
    assert "[FAIL] missing entrypoint" in captured.out
    assert "Project status: FAILED" in captured.err
