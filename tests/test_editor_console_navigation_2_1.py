from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_console_navigation21 import (
    EditorSourceLocation,
    resolve_project_source,
    source_location_from_exception,
)
from swirengine.editor_diagnostics import EditorConsole
from swirengine.editor_preview import DEFAULT_EDITOR_FIXED_STEP
from swirengine.editor_runtime import EditorRuntimeMode


def _load_source_module(source: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_console_entries_preserve_structured_source_locations_and_filter_by_path() -> None:
    console = EditorConsole()
    entry = console.write(
        "player update failed",
        level="error",
        source="runtime",
        timestamp=1.0,
        path="scripts/player.py",
        line=17,
        column=9,
    )

    assert entry.has_source_location
    assert entry.path == "scripts/player.py"
    assert entry.line == 17
    assert entry.column == 9
    assert console.frame(query="player.py").entries == (entry,)

    with pytest.raises(ValueError, match="source path cannot be empty"):
        console.write("bad", path="  ")
    with pytest.raises(ValueError, match="line must be at least 1"):
        console.write("bad", path="scripts/player.py", line=0)
    with pytest.raises(ValueError, match="requires a source path"):
        console.write("bad", line=1)


def test_source_location_from_exception_prefers_deepest_project_frame(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "player.py"
    source.parent.mkdir(parents=True)
    source.write_text("def boom():\n    raise RuntimeError('boom')\nboom()\n", encoding="utf-8")

    try:
        _load_source_module(source, "_swir_console_location_boom")
    except RuntimeError as exc:
        location = source_location_from_exception(tmp_path, exc)
    else:  # pragma: no cover - defensive guard for the fixture itself
        raise AssertionError("fixture did not raise")

    assert location is not None
    assert location.path == "scripts/player.py"
    assert location.line == 2


def test_project_runtime_error_is_routed_with_source_location(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("ConsoleLocation", "2d")
    source = root / "scripts" / "player.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def explode(_dt):\n    raise RuntimeError('project boom')\n", encoding="utf-8")
    module = _load_source_module(source, "_swir_console_location_player")
    explode = module.explode
    assert callable(explode)

    session = EditorProjectSession.open(root)
    preview = session.controller.preview
    assert preview is not None
    session.console.clear()
    monkeypatch.setattr(preview.runtime, "update", explode)

    assert session.controller.play_pause() is EditorRuntimeMode.PLAYING
    assert not session.controller.update_runtime(DEFAULT_EDITOR_FIXED_STEP)

    [entry] = session.console.entries
    assert entry.message == "Runtime update failed: RuntimeError: project boom"
    assert entry.path == "scripts/player.py"
    assert entry.line == 2


def test_project_source_resolution_is_project_scoped_and_requires_a_file(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "player.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('ok')\n", encoding="utf-8")

    relative = EditorSourceLocation("scripts/player.py", 1, 1)
    absolute = EditorSourceLocation(str(source), 1)

    assert resolve_project_source(tmp_path, relative) == source.resolve()
    assert resolve_project_source(tmp_path, absolute) == source.resolve()
    assert resolve_project_source(tmp_path, EditorSourceLocation("../escape.py", 1)) is None
    assert resolve_project_source(tmp_path, EditorSourceLocation("scripts/missing.py", 1)) is None


def test_editor_source_location_display_is_stable() -> None:
    assert EditorSourceLocation("main.py").display == "main.py"
    assert EditorSourceLocation("main.py", 7).display == "main.py:7"
    assert EditorSourceLocation("main.py", 7, 3).display == "main.py:7:3"
