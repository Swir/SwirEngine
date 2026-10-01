from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from swirengine.core.scene import Scene
from swirengine.editor_lighting22 import LightingScenePreview22, LightingSceneSource22
from swirengine.editor_lighting_frontend22 import TkLightingEditorApp22
from swirengine.editor_preview import EditorViewportImage
from swirengine.editor_vfx_frontend22 import TkVFXEditorApp22
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D
from swirengine.lighting_authoring22 import EditorLightingTooling22
from swirengine.serialization import SceneSerializer


def test_native_tk_lighting_controls_scene_switch_close_reopen(tmp_path: Path, monkeypatch) -> None:
    if os.environ.get("SWIR_LIGHTING_REQUIRE_TK") != "1":
        pytest.skip("required by the dedicated Xvfb native Tk workflow")
    import tkinter as tk
    from tkinter import messagebox, ttk

    # Isolate the new native panel from unrelated creator tool constructor arguments.
    # Widgets, callbacks and event loop are real Tk; rendering has separate mandatory EGL tests.
    def init_base(self, controller, **kwargs):
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.controller = controller
        self.root = tk.Tk()
        self.root.geometry("200x100")
    monkeypatch.setattr(TkVFXEditorApp22, "__init__", init_base)
    class Probe(LightingScenePreview22):
        def capture(self, width, height, camera):
            self.frames += 1
            return EditorViewportImage(2, 2, b"\x66" * 12)

    scene = Scene()
    scene.add(Cube3D())
    active = [LightingSceneSource22("scene", "3d", scene, Camera3D(), SceneSerializer())]
    errors = []
    console = SimpleNamespace(write=lambda *args, **kwargs: errors.append(args))
    app = TkLightingEditorApp22(SimpleNamespace(console=console),
                                lighting=EditorLightingTooling22(tmp_path),
                                lighting_source=lambda: active[0])
    app.lighting_controller._preview_factory = Probe
    callbacks = []
    app.root.report_callback_exception = lambda *args: callbacks.append(args)
    try:
        app._open_lighting_editor()
        app.root.update()
        window = app._lighting_window
        assert len(app._lighting_notebook.tabs()) == 5
        assert window.winfo_width() >= 1060
        app._lighting_fields["light"]["intensity"][0].set("2.0")
        app._lighting_apply_light()
        assert app.lighting_controller.spec().lights[0].intensity == 2.0
        assert app._lighting_fields["light"]["intensity"][0].get() == "2.0"
        assert app._lighting_light_list.get(app._lighting_light_list.curselection()[0]) == "sun"
        app._lighting_fields["Color grading"]["exposure"][0].set("1.7")
        app._lighting_apply("postfx", "Color grading")
        app._lighting_save()
        assert not app.lighting_controller.tooling.dirty
        app._lighting_start()
        app._capture_lighting()
        assert app._lighting_photo is not None
        app._lighting_pause()
        app._lighting_step()
        assert not app.lighting_controller.running
        active[0] = replace(active[0], key="other-scene", scene=Scene())
        # An Apply click can arrive before the next scene polling tick.
        app._lighting_apply("postfx", "Color grading")
        assert len(errors) == 1 and "Active scene changed" in errors[0][0]
        assert all(spec.scene != "other-scene" for spec in app.lighting_controller.tooling.profiles())
        errors.clear()
        app.root.after_cancel(app._lighting_after)
        app._lighting_after = None
        app._lighting_tick()
        assert not app.lighting_controller.active
        assert "other-scene" in app._lighting_scene_var.get()
        assert app._lighting_photo is None
        app._close_lighting_editor()
        assert app._lighting_window is None and app._lighting_after is None
        app._open_lighting_editor()
        app.root.update()
        assert app._lighting_window is not window
        assert not app.lighting_controller.active
        assert not callbacks and not errors
    finally:
        app._close_lighting_editor()
        app.root.destroy()


@pytest.mark.parametrize("mode", ("2d", "3d"))
def test_unified_native_shell_routes_lighting_to_active_project(
    tmp_path: Path, monkeypatch, mode: str,
) -> None:
    if os.environ.get("SWIR_LIGHTING_REQUIRE_TK") != "1":
        pytest.skip("required by the dedicated Xvfb native Tk workflow")
    from swirengine.editor_asset_app21 import TkIntegratedEditorApp21, run_editor_session21
    from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
    from swirengine.project_scaffold21 import new_project21

    root = new_project21("NativeLighting", mode, parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    visited = []

    def exercise(self):
        # The full unified constructor and real Tk widgets run unmodified.
        # Replace only the unbounded mainloop with a finite sequence of UI actions.
        try:
            self._open_lighting_editor()
            self.root.update()
            source = self.lighting_controller.source()
            assert source.scene is session.workspace.scene
            assert source.key == session.scenes.active_path
            assert source.mode == mode
            assert len(self._lighting_notebook.tabs()) == 5
            self._lighting_fields["Color grading"]["exposure"][0].set("1.9")
            self._lighting_apply("postfx", "Color grading")
            assert session.lighting.require(source.key).postfx.exposure == 1.9
            assert session.summary().dirty
            self._lighting_save()
            assert not session.lighting.dirty
            visited.append(source.key)
        finally:
            self.close()

    monkeypatch.setattr(TkIntegratedEditorApp21, "run", exercise)
    run_editor_session21(session)
    assert visited == [session.scenes.active_path]
    reopened = EditorIntegratedProjectSession21.open(root)
    assert reopened.lighting.require(visited[0]).postfx.exposure == 1.9
