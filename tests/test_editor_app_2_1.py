from __future__ import annotations

from pathlib import Path

import pytest

from swirengine import Color, Rectangle2D
from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectOpenError, EditorProjectSession, main
from swirengine.editor_preview import DEFAULT_EDITOR_FIXED_STEP
from swirengine.editor_runtime import EditorRuntimeMode


class FakeLiveBackend:
    def __init__(self) -> None:
        self.viewport = object()
        self.release_calls = 0

    def release(self) -> None:
        self.release_calls += 1


def test_editor_session_opens_manifest_project_and_reports_creator_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorStart", "2d")

    session = EditorProjectSession.open(root)
    summary = session.summary()

    assert summary.project_name == "EditorStart"
    assert summary.mode == "2d"
    assert summary.scene_path == "scenes/main.swirscene"
    assert summary.object_count == 0
    assert summary.entity_count == 0
    assert summary.asset_count == 0
    assert not summary.scene_exists
    assert not summary.editor_state_exists
    assert session.controller.preview is not None
    assert session.controller.preview.viewport is None


def test_editor_session_wires_runtime_profiler_into_production_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorProfile", "2d")
    session = EditorProjectSession.open(root)
    preview = session.controller.preview

    assert preview is not None
    assert preview.profiler is session.profiler.profiler
    assert session.controller.play_pause() is EditorRuntimeMode.PLAYING
    assert session.controller.update_runtime(DEFAULT_EDITOR_FIXED_STEP)

    profile = session.profiler.frame()
    assert profile.sample_count == 1
    assert profile.latest.frame_ms == pytest.approx(DEFAULT_EDITOR_FIXED_STEP * 1000.0)
    assert profile.latest.fps == pytest.approx(60.0)


def test_editor_session_routes_runtime_failures_to_production_console(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorFailure", "2d")
    session = EditorProjectSession.open(root)
    preview = session.controller.preview

    assert preview is not None
    session.console.clear()
    assert session.controller.play_pause() is EditorRuntimeMode.PLAYING

    def explode(_dt: float) -> bool:
        raise RuntimeError("game update exploded")

    monkeypatch.setattr(preview.runtime, "update", explode)

    assert not session.controller.update_runtime(DEFAULT_EDITOR_FIXED_STEP)
    assert preview.runtime.mode is EditorRuntimeMode.EDIT
    assert session.profiler.frame().sample_count == 0

    entries = session.console.entries
    assert len(entries) == 1
    assert entries[0].level == "error"
    assert entries[0].source == "runtime"
    assert entries[0].message == "Runtime update failed: RuntimeError: game update exploded"
    assert preview.last_error == entries[0].message


def test_editor_session_exercises_milestone_7_play_debug_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorMilestone7", "2d")
    session = EditorProjectSession.open(root)
    preview = session.controller.preview

    assert preview is not None
    frame = session.controller.frame()
    assert frame.console is not None
    assert frame.profiler is not None
    assert frame.preview is not None
    assert preview.runtime.mode is EditorRuntimeMode.EDIT

    assert session.controller.play_pause() is EditorRuntimeMode.PLAYING
    assert session.controller.update_runtime(DEFAULT_EDITOR_FIXED_STEP)
    assert session.controller.play_pause() is EditorRuntimeMode.PAUSED
    first_sample_count = session.profiler.frame().sample_count
    assert first_sample_count == 1

    assert session.controller.step()
    assert preview.runtime.mode is EditorRuntimeMode.PAUSED
    assert session.profiler.frame().sample_count == first_sample_count + 1

    assert session.controller.stop()
    assert preview.runtime.mode is EditorRuntimeMode.EDIT
    final_frame = session.controller.frame()
    assert final_frame.preview is not None
    assert final_frame.preview.runtime.mode is EditorRuntimeMode.EDIT


def test_editor_session_saves_scene_and_portable_editor_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorSave", "2d")
    session = EditorProjectSession.open(root)
    player = session.workspace.scene.add(
        Rectangle2D(10, 20, 48, 32, Color(0.1, 0.7, 1.0, 1.0), name="Player")
    )
    session.workspace.select(player)
    session.workspace.configure_viewport(mode="2d", snap_enabled=True, translation_snap=8.0)

    state = session.save()

    assert session.scene_path.is_file()
    assert session.state_path.is_file()
    assert state.project_name == "EditorSave"
    assert state.active_scene_id == "scenes/main.swirscene"

    reopened = EditorProjectSession.open(root)
    frame = reopened.workspace.frame()
    assert len(reopened.workspace.scene.objects) == 1
    assert frame.inspector is not None
    assert frame.inspector.type_name == "Rectangle2D"
    assert frame.viewport.mode == "2d"
    assert frame.viewport.snap_enabled
    assert frame.viewport.translation_snap == 8.0


def test_editor_session_attaches_and_releases_live_viewport_lazily(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("LiveViewport", "3d")
    session = EditorProjectSession.open(root)
    backend = FakeLiveBackend()

    attached = session.enable_live_viewport(backend)  # type: ignore[arg-type]

    assert attached is backend
    assert session.controller.preview is not None
    assert session.controller.preview.viewport is backend.viewport
    session.disable_live_viewport()
    assert session.controller.preview.viewport is None
    assert backend.release_calls == 1
    session.disable_live_viewport()
    assert backend.release_calls == 1


def test_editor_session_rejects_project_escape_scene_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorSafe", "3d")

    with pytest.raises(ValueError, match="project-relative"):
        EditorProjectSession.open(root, scene="../outside.swirscene")


def test_editor_session_fails_closed_on_invalid_serialized_scene(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorBroken", "2d")
    scene = root / "scenes" / "main.swirscene"
    scene.write_text("not json", encoding="utf-8")

    with pytest.raises(EditorProjectOpenError, match="cannot load editor scene"):
        EditorProjectSession.open(root)


def test_swireditor_headless_cli_works_without_window_system(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("HeadlessEditor", "3d")

    assert main([str(root), "--headless"]) == 0

    output = capsys.readouterr().out
    assert "SwirEditor 2.1 project: HeadlessEditor (3d)" in output
    assert "Scene: scenes/main.swirscene" in output
    assert "Assets: 0" in output
