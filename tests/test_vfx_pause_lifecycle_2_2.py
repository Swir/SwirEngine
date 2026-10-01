from __future__ import annotations

from pathlib import Path

from swirengine.editor_vfx22 import EditorVFXPanelController22
from swirengine.vfx_authoring22 import EditorVFXTooling22


def test_vfx_pause_preserves_runtime_for_bounded_manual_step(tmp_path: Path) -> None:
    controller = EditorVFXPanelController22(EditorVFXTooling22(tmp_path))
    controller.create("smoke", preset="soft-smoke-2d")

    started = controller.start_preview()
    assert started.preview_running
    assert started.diagnostics is not None

    paused = controller.pause_preview()
    assert not paused.preview_running
    assert paused.diagnostics is not None
    before_visits = paused.diagnostics.work_visits_or_frames

    stepped = controller.step_preview(1.0 / 60.0)
    assert not stepped.preview_running
    assert stepped.diagnostics is not None
    assert stepped.diagnostics.work_visits_or_frames >= before_visits
    assert stepped.diagnostics.last_step > 0.0
