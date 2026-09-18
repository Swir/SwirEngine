from __future__ import annotations

from pathlib import Path

from swirengine.exporting import PackagingProfile, ProjectExporter


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "main.py").write_text("print('game')\n", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "sprite.txt").write_text("asset\n", encoding="utf-8")
    return root


def test_export_detects_semantic_scenes_table_with_toml_whitespace(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    levels = root / "levels"
    levels.mkdir()
    (levels / "intro.swirscene").write_text("scene\n", encoding="utf-8")
    (root / "swirproject.toml").write_text(
        """
name = "Demo"

[ scenes ]
boot = "intro"

[ scenes.registry.intro ]
path = "levels/intro.swirscene"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    assert Path("levels/intro.swirscene") in plan.files


def test_export_does_not_activate_scenes_from_multiline_string(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    (root / "swirproject.toml").write_text(
        '''
[legacy]
format = "pre-1.9"
note = """
[scenes]
[scenes.registry.fake]
"""
'''.strip()
        + "\n",
        encoding="utf-8",
    )

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    assert Path("swirproject.toml") in plan.files
    assert Path("assets/sprite.txt") in plan.files


def test_export_preserves_malformed_legacy_manifest_behavior(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    (root / "swirproject.toml").write_text("legacy = [unterminated\n", encoding="utf-8")

    plan = ProjectExporter(root).plan(PackagingProfile(include=("assets",)))

    assert Path("swirproject.toml") in plan.files
    assert Path("assets/sprite.txt") in plan.files
