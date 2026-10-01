from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from swirengine.editor_lighting_frontend22 import TkLightingEditorApp22
from swirengine.editor_preview import EditorViewportImage
from swirengine.editor_ui_designer22 import UIDesignerPreview22
from swirengine.editor_ui_designer_frontend22 import TkUIDesignerEditorApp22
from swirengine.ui_designer22 import (
    EditorUIDesignerTooling22,
    UIAnimationKeyframeSpec22,
    UIAnimationSpec22,
    UIAnimationTrackSpec22,
    UIWidgetSpec22,
)


def test_native_tk_ui_designer_preview_close_and_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.environ.get("SWIR_UI_DESIGNER_REQUIRE_TK") != "1":
        pytest.skip("required by the dedicated Xvfb native Tk workflow")
    import tkinter as tk
    from tkinter import messagebox, ttk

    def init_base(self, controller, **kwargs):
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.controller = controller
        self.root = tk.Tk()
        self.root.geometry("220x120")

    monkeypatch.setattr(TkLightingEditorApp22, "__init__", init_base)

    class Probe(UIDesignerPreview22):
        def capture(self, width: int, height: int) -> EditorViewportImage:
            if self.closed:
                raise RuntimeError("closed preview")
            self.runtime.layout(width, height)
            self.frames += 1
            return EditorViewportImage(2, 2, b"\x77" * 12)

    errors: list[tuple[object, ...]] = []
    console = SimpleNamespace(write=lambda *args, **kwargs: errors.append(args))
    app = TkUIDesignerEditorApp22(
        SimpleNamespace(console=console),
        ui_designer=EditorUIDesignerTooling22(tmp_path),
    )
    app.ui_designer_controller._preview_factory = Probe
    app.ui_designer_controller.upsert_widget(
        UIWidgetSpec22("play", "button", text="Play", action="play-game")
    )
    app.ui_designer_controller.upsert_animation(
        UIAnimationSpec22(
            "pulse",
            1.0,
            (
                UIAnimationTrackSpec22(
                    "play",
                    "opacity",
                    (
                        UIAnimationKeyframeSpec22(0.0, 1.0),
                        UIAnimationKeyframeSpec22(1.0, 0.5),
                    ),
                ),
            ),
        )
    )
    callbacks: list[tuple[object, ...]] = []
    app.root.report_callback_exception = lambda *args: callbacks.append(args)
    try:
        app._open_ui_designer()
        app.root.update()
        first_window = app._ui_designer_window
        assert len(app._ui_designer_notebook.tabs()) == 3
        assert first_window.winfo_width() >= 1040
        app._ui_designer_animation_list.selection_set(0)
        app._ui_designer_start()
        preview = app.ui_designer_controller.preview
        app._capture_ui_designer()
        assert app._ui_designer_photo is not None

        app._ui_designer_pause()
        paused_time = app.ui_designer_controller.frame().preview_time
        app._ui_designer_step()
        assert app.ui_designer_controller.frame().preview_time > paused_time
        assert not app.ui_designer_controller.running
        app._ui_designer_seek_var.set("0.25")
        app._ui_designer_seek()
        assert app.ui_designer_controller.frame().preview_time == pytest.approx(0.25)

        app._close_ui_designer()
        app.root.update()
        assert app._ui_designer_window is None and app._ui_designer_after is None
        assert preview is not None and preview.closed
        app._open_ui_designer()
        app.root.update()
        assert app._ui_designer_window is not first_window
        assert not app.ui_designer_controller.active
        assert not callbacks and not errors
    finally:
        app._close_ui_designer()
        app.root.destroy()
