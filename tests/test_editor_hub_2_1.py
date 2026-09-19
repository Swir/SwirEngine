from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.cli21 import editor_entry
from swirengine.cli21 import main as cli_main
from swirengine.project_hub21 import EditorProjectHub, RecentProjectsStore
from swirengine.project_scaffold21 import new_project21


def test_recent_projects_store_is_bounded_deduplicated_and_prunes_missing(tmp_path: Path) -> None:
    roots = [new_project21(f"Recent{index}", "2d", parent=tmp_path) for index in range(3)]
    store = RecentProjectsStore(tmp_path / "recent.json", limit=2)

    store.record(roots[0])
    store.record(roots[1])
    store.record(roots[0])
    assert store.load() == (roots[0].resolve(), roots[1].resolve())

    store.record(roots[2])
    assert store.load() == (roots[2].resolve(), roots[0].resolve())
    (roots[2] / "swirproject.toml").unlink()
    assert store.load() == (roots[0].resolve(),)


def test_project_hub_creates_opens_and_records_recent_projects(tmp_path: Path) -> None:
    store = RecentProjectsStore(tmp_path / "recent.json")
    hub = EditorProjectHub(store)

    created = hub.create_project("HubGame", "3d", parent=tmp_path)
    reopened = hub.open_project(created.manifest.root)

    assert created.manifest.mode == "3d"
    assert reopened.manifest.name == "HubGame"
    assert hub.recent_projects() == (created.manifest.root.resolve(),)
    manifest = (created.manifest.root / "swirproject.toml").read_text(encoding="utf-8")
    assert 'engine = ">=2.0,<3.0"' in manifest


def test_project_hub_rejects_parent_escape(tmp_path: Path) -> None:
    hub = EditorProjectHub(RecentProjectsStore(tmp_path / "recent.json"))

    with pytest.raises(ValueError, match="single directory name"):
        hub.create_project("../escape", "2d", parent=tmp_path)


def test_unified_new_command_declares_2_x_engine_range(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli_main(["new", "UnifiedNew", "--mode", "3d"]) == 0

    manifest = (tmp_path / "UnifiedNew" / "swirproject.toml").read_text(encoding="utf-8")
    assert 'name = "UnifiedNew"' in manifest
    assert 'mode = "3d"' in manifest
    assert 'engine = ">=2.0,<3.0"' in manifest
    assert "Created 3D project:" in capsys.readouterr().out


def test_swirengine_editor_subcommand_uses_same_headless_editor_flow(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project21("UnifiedEditor", "2d")

    assert cli_main(["editor", str(root), "--headless"]) == 0
    output = capsys.readouterr().out
    assert "SwirEditor 2.1 project: UnifiedEditor (2d)" in output


def test_unified_cli_delegates_established_commands(capsys) -> None:
    assert cli_main(["info"]) == 0
    assert "SwirEngine 2.0.0" in capsys.readouterr().out


def test_standalone_editor_entry_uses_same_headless_router(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project21("StandaloneEditor", "3d")

    assert editor_entry([str(root), "--headless"]) == 0
    assert "SwirEditor 2.1 project: StandaloneEditor (3d)" in capsys.readouterr().out
