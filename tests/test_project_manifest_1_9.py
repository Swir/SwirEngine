from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.cli import main, new_project
from swirengine.exporting import ExportTarget
from swirengine.project19 import ProjectManifest, ProjectManifestError


def _write_project(root: Path, manifest: str) -> Path:
    root.mkdir()
    (root / "main.py").write_text("print('game')\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "scenes").mkdir()
    (root / "scripts").mkdir()
    (root / "swirproject.toml").write_text(manifest, encoding="utf-8")
    return root


def test_legacy_manifest_remains_supported(tmp_path: Path) -> None:
    root = _write_project(
        tmp_path / "legacy",
        'name = "Legacy"\nmode = "2d"\nengine = ">=1.0,<2.0"\n',
    )

    manifest = ProjectManifest.load(root)

    assert manifest.name == "Legacy"
    assert manifest.mode == "2d"
    assert manifest.entrypoint == "main.py"
    assert manifest.include == ("assets", "scenes", "scripts")
    assert manifest.profiles == {}


def test_rich_manifest_build_profile_maps_to_existing_export_contract(tmp_path: Path) -> None:
    root = _write_project(
        tmp_path / "rich",
        """
[project]
name = "Real Game"
mode = "3d"
engine = ">=1.0,<2.0"
entrypoint = "main.py"

[content]
include = ["assets", "scenes", "scripts"]

[profiles.linux]
target = "linux"
app_name = "Real Game"
onefile = true
console = false

[profiles.linux.metadata]
channel = "playtest"
""".strip()
        + "\n",
    )

    manifest = ProjectManifest.load(root)
    profile = manifest.packaging_profile("linux")

    assert profile.target is ExportTarget.LINUX
    assert profile.entrypoint == "main.py"
    assert profile.include == ("assets", "scenes", "scripts")
    assert profile.onefile is True
    assert profile.console is False
    assert profile.metadata == {"channel": "playtest"}


@pytest.mark.parametrize(
    "value",
    ["../outside.py", "/tmp/outside.py", r"C:\outside.py", "//server/share.py"],
)
def test_manifest_rejects_paths_that_escape_project(tmp_path: Path, value: str) -> None:
    root = _write_project(
        tmp_path / "unsafe",
        f'name = "Unsafe"\nmode = "2d"\nentrypoint = "{value.replace(chr(92), chr(92) * 2)}"\n',
    )

    with pytest.raises(ProjectManifestError, match="inside the project"):
        ProjectManifest.load(root)


def test_manifest_fingerprint_is_portable_and_stable(tmp_path: Path) -> None:
    manifest_text = """
name = "Fingerprint"
mode = "2d"
engine = ">=1.0,<2.0"
entrypoint = "main.py"

[profiles.windows]
target = "windows"
metadata = { channel = "qa", lane = "nightly" }
""".strip()
    left = _write_project(tmp_path / "left", manifest_text)
    right = _write_project(tmp_path / "right", manifest_text)

    assert ProjectManifest.load(left).fingerprint == ProjectManifest.load(right).fingerprint


def test_doctor_reports_missing_runtime_files_without_crashing(tmp_path: Path) -> None:
    root = tmp_path / "broken"
    root.mkdir()
    (root / "swirproject.toml").write_text(
        'name = "Broken"\nentrypoint = "missing.py"\n',
        encoding="utf-8",
    )

    diagnostics = ProjectManifest.load(root).diagnostics()

    assert any(item.code == "entrypoint-missing" and item.severity == "error" for item in diagnostics)


def test_new_project_is_immediately_doctor_ready(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("ProductionGame", "3d")
    manifest = ProjectManifest.load(root)

    assert {"windows", "linux", "macos"} == set(manifest.profiles)
    assert main(["doctor", str(root), "--profile", "linux"]) == 0
    assert "Project manifest OK" in capsys.readouterr().out


def test_profile_driven_export_uses_manifest_without_requiring_target(
    tmp_path: Path, capsys
) -> None:
    root = _write_project(
        tmp_path / "exportable",
        """
name = "Exportable"
mode = "2d"
entrypoint = "main.py"

[profiles.linux]
target = "linux"
app_name = "Exportable"
onefile = false
console = true
""".strip()
        + "\n",
    )
    output = tmp_path / "stage"

    assert main(["export", str(root), "--profile", "linux", "--output", str(output)]) == 0
    assert (output / "main.py").is_file()
    assert (output / "swir-export.json").is_file()
    assert "Exported linux" in capsys.readouterr().out


def test_export_still_requires_target_without_manifest_profile(tmp_path: Path, capsys) -> None:
    root = _write_project(tmp_path / "legacy-export", 'name = "Legacy"\n')

    assert main(["export", str(root)]) == 2
    assert "--target is required" in capsys.readouterr().err


def test_unknown_profile_has_actionable_error(tmp_path: Path) -> None:
    root = _write_project(tmp_path / "unknown", 'name = "Unknown"\n')

    with pytest.raises(ProjectManifestError, match="available profiles"):
        ProjectManifest.load(root).packaging_profile("shipping")
