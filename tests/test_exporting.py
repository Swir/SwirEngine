from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swirengine.exporting import (
    ExportTarget,
    NativeBuildError,
    PackagingProfile,
    ProjectExporter,
)


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
    assert "swirengine-build.spec" in plan.native_build_command


def test_export_without_scene_registry_preserves_legacy_manifest_behavior(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    (root / "swirproject.toml").write_text(
        '[legacy]\nformat = "pre-1.9"\n',
        encoding="utf-8",
    )

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    assert Path("swirproject.toml") in plan.files
    assert Path("assets/sprite.txt") in plan.files


def test_export_plan_stages_declared_scene_package_files(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    levels = root / "levels"
    levels.mkdir()
    (levels / "intro.swirscene").write_text("scene", encoding="utf-8")
    (levels / "crate.swirprefab").write_text("prefab", encoding="utf-8")
    (root / "swirproject.toml").write_text(
        """
name = "Demo"

[scenes]
boot = "intro"

[scenes.registry.intro]
path = "levels/intro.swirscene"
prefabs = ["levels/crate.swirprefab"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    files = {path.as_posix() for path in plan.files}
    assert "levels/intro.swirscene" in files
    assert "levels/crate.swirprefab" in files


def test_export_rejects_invalid_or_excluded_scene_package_content(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    (root / "swirproject.toml").write_text(
        """
name = "Demo"

[scenes]
boot = "intro"

[scenes.registry.intro]
path = "levels/intro.swirscene"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="scene package export preflight failed"):
        ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    levels = root / "levels"
    levels.mkdir()
    (levels / "intro.swirscene").write_text("scene", encoding="utf-8")
    with pytest.raises(ValueError, match="excludes declared scene package content"):
        ProjectExporter(root).plan(
            PackagingProfile(include=("assets",), exclude=("levels",))
        )


def test_export_rejects_scene_package_dependency_cycle(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    levels = root / "levels"
    levels.mkdir()
    (levels / "intro.swirscene").write_text("scene", encoding="utf-8")
    (levels / "arena.swirscene").write_text("scene", encoding="utf-8")
    (root / "swirproject.toml").write_text(
        """
name = "Demo"

[scenes]
boot = "intro"

[scenes.registry.intro]
path = "levels/intro.swirscene"
depends_on = ["arena"]

[scenes.registry.arena]
path = "levels/arena.swirscene"
depends_on = ["intro"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        ProjectExporter(root).plan(PackagingProfile(include=("assets",)))


def test_desktop_export_writes_portable_spec_checksums_and_manifest_v2(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    profile = PackagingProfile(name="desktop-demo", target=ExportTarget.LINUX)

    result = ProjectExporter(root).export(profile, tmp_path / "export")
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

    assert result.experimental is False
    assert result.native_spec is not None
    assert result.native_spec.is_file()
    spec = result.native_spec.read_text(encoding="utf-8")
    assert "assets/sprite.txt" in spec
    assert "COLLECT(" in spec
    assert manifest["version"] == 2
    assert manifest["native_spec"] == "swirengine-build.spec"
    assert manifest["sha256"]["assets/sprite.txt"] == hashlib.sha256(b"asset").hexdigest()


def test_onefile_spec_embeds_binaries_and_data_in_executable(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    profile = PackagingProfile(name="single", target=ExportTarget.LINUX, onefile=True)

    result = ProjectExporter(root).export(profile, tmp_path / "export")
    assert result.native_spec is not None
    spec = result.native_spec.read_text(encoding="utf-8")

    assert "a.binaries, a.datas" in spec
    assert "COLLECT(" not in spec


def test_export_copies_files_and_writes_manifest(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    profile = PackagingProfile(name="web-demo", target=ExportTarget.WEB)

    result = ProjectExporter(root).export(profile, tmp_path / "export")
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

    assert result.experimental is True
    assert result.native_build_command is None
    assert result.native_spec is None
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


def test_export_rejects_paths_that_escape_project(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    exporter = ProjectExporter(root)

    with pytest.raises(ValueError, match="inside the project"):
        exporter.plan(PackagingProfile(entrypoint="../secret.py"))
    with pytest.raises(ValueError, match="inside the project"):
        exporter.plan(PackagingProfile(include=("../secret",)))


def test_native_build_rejects_cross_compile_and_non_desktop(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path / "project")
    exporter = ProjectExporter(root)
    monkeypatch.setattr("swirengine.exporting.sys.platform", "linux")

    with pytest.raises(NativeBuildError, match="matching host"):
        exporter.build_native(PackagingProfile(target=ExportTarget.WINDOWS))
    with pytest.raises(NativeBuildError, match="not available"):
        exporter.build_native(PackagingProfile(target=ExportTarget.WEB))


def test_native_build_uses_current_python_and_requires_artifact(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path / "project")
    exporter = ProjectExporter(root)
    monkeypatch.setattr("swirengine.exporting.sys.platform", "linux")
    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_runner(command, *, cwd, capture_output, text, check):
        assert capture_output is True
        assert text is True
        assert check is False
        native_dist = Path(cwd) / "native-dist"
        native_dist.mkdir()
        (native_dist / "demo").write_text("binary", encoding="utf-8")
        calls.append((tuple(command), Path(cwd)))
        return SimpleNamespace(returncode=0, stderr="")

    result = exporter.build_native(
        PackagingProfile(name="demo", target=ExportTarget.LINUX),
        tmp_path / "native-export",
        runner=fake_runner,
    )

    assert result.returncode == 0
    assert result.command[0].endswith(("python", "python.exe")) or "python" in result.command[0].lower()
    assert result.artifacts == (result.export.output_dir / "native-dist" / "demo",)
    assert calls[0][1] == result.export.output_dir


def test_profile_validation() -> None:
    with pytest.raises(ValueError, match="profile name"):
        PackagingProfile(name=" ")
    with pytest.raises(ValueError, match="entrypoint"):
        PackagingProfile(entrypoint=" ")
