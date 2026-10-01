from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.editor_asset_app21 import TkIntegratedEditorApp21
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_vfx22 import (
    MAX_VFX_PREVIEW_BURST,
    MAX_VFX_PREVIEW_STEP,
    EditorVFXPanelController22,
)
from swirengine.editor_vfx_frontend22 import TkVFXEditorApp22
from swirengine.gpu_particles import GPUParticleEmitter3D
from swirengine.particles import ParticleEmitter2D
from swirengine.project_scaffold21 import new_project21
from swirengine.vfx_schema22 import EditorVFXError22


@pytest.mark.parametrize(
    ("mode", "preset", "runtime_type"),
    (
        ("2d", "sparks-2d", ParticleEmitter2D),
        ("3d", "fire-gpu", GPUParticleEmitter3D),
    ),
)
def test_representative_project_vfx_round_trip_and_runtime_preview(
    tmp_path: Path,
    mode: str,
    preset: str,
    runtime_type: type[ParticleEmitter2D | GPUParticleEmitter3D],
) -> None:
    root = new_project21(f"VFXGate{mode.upper()}", mode, parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    controller = EditorVFXPanelController22(session.vfx)
    controller.create("primary", preset=preset)

    first_preview = session.vfx.preview("primary")
    assert isinstance(first_preview.runtime, runtime_type)
    controller.start_preview()
    controller.burst(24)
    frame = controller.step_preview(1.0 / 60.0)
    assert frame.diagnostics is not None
    assert frame.diagnostics.emitted_total >= 24
    assert session.summary().dirty

    session.save()
    canonical = (root / "config" / "vfx.json").read_bytes()

    reopened = EditorIntegratedProjectSession21.open(root)
    reopened_controller = EditorVFXPanelController22(reopened.vfx)
    reopened_controller.select("primary")
    second_preview = reopened.vfx.preview("primary")
    assert isinstance(second_preview.runtime, runtime_type)
    assert second_preview.fingerprint == first_preview.fingerprint
    assert not reopened.summary().dirty

    initial = reopened_controller.start_preview()
    assert initial.diagnostics is not None
    reopened_controller.burst(24)
    stepped = reopened_controller.step_preview(1.0 / 60.0)
    assert stepped.diagnostics is not None
    assert stepped.diagnostics.emitted_total >= 24

    paused = reopened_controller.pause_preview()
    assert not paused.preview_running
    assert paused.diagnostics == stepped.diagnostics

    restarted = reopened_controller.start_preview()
    assert restarted.preview_running
    assert restarted.diagnostics == initial.diagnostics
    reopened_controller.burst(24)
    replayed = reopened_controller.step_preview(1.0 / 60.0)
    assert replayed.diagnostics == stepped.diagnostics
    assert not reopened.summary().dirty
    assert reopened.vfx.preview("primary").fingerprint == first_preview.fingerprint

    reopened.vfx.save()
    assert (root / "config" / "vfx.json").read_bytes() == canonical


@pytest.mark.parametrize(("mode", "preset"), (("2d", "sparks-2d"), ("3d", "fire-gpu")))
@pytest.mark.parametrize("count", (1.5, "12", True))
def test_vfx_preview_burst_rejects_non_integer_counts(
    tmp_path: Path,
    mode: str,
    preset: str,
    count: object,
) -> None:
    root = new_project21("VFXBurstValidation", mode, parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    controller = EditorVFXPanelController22(session.vfx)
    controller.create("primary", preset=preset)
    session.save()
    canonical = (root / "config" / "vfx.json").read_bytes()
    controller.start_preview()
    before = controller.burst(3)
    status = controller.status
    assert before.diagnostics is not None

    with pytest.raises(EditorVFXError22, match="preview burst count must be an integer"):
        controller.burst(count)

    assert controller.frame() == before
    assert controller.status == status
    assert not session.summary().dirty
    assert (root / "config" / "vfx.json").read_bytes() == canonical


@pytest.mark.parametrize(("mode", "preset"), (("2d", "sparks-2d"), ("3d", "fire-gpu")))
@pytest.mark.parametrize("paused", (False, True))
def test_representative_vfx_clear_resets_bounded_runtime_diagnostics(
    tmp_path: Path,
    mode: str,
    preset: str,
    paused: bool,
) -> None:
    root = new_project21("VFXClearLifecycle", mode, parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    controller = EditorVFXPanelController22(session.vfx)
    controller.create("primary", preset=preset)
    session.save()
    canonical = (root / "config" / "vfx.json").read_bytes()
    inactive = controller.frame()
    with pytest.raises(EditorVFXError22, match="VFX preview is not active"):
        controller.clear_preview()
    assert controller.frame() == inactive

    controller.start_preview()
    controller.burst(MAX_VFX_PREVIEW_BURST * 100)
    before = controller.step_preview(MAX_VFX_PREVIEW_STEP * 2)
    assert before.diagnostics is not None
    assert 0 < before.diagnostics.active_or_queued <= before.diagnostics.capacity
    assert before.diagnostics.last_step == pytest.approx(MAX_VFX_PREVIEW_STEP)
    assert before.diagnostics.step_was_clamped
    if paused:
        controller.pause_preview()

    cleared = controller.clear_preview()
    assert cleared.preview_running is (not paused)
    assert cleared.selected == "primary"
    assert cleared.backend == before.backend
    assert cleared.diagnostics is not None
    assert cleared.diagnostics.capacity == before.diagnostics.capacity
    assert cleared.diagnostics.active_or_queued == 0
    assert cleared.diagnostics.work_visits_or_frames == 0
    assert cleared.diagnostics.last_step == 0.0
    assert not cleared.diagnostics.step_was_clamped
    # Clear removes live work, not the runtime's lifetime emission counter.
    assert cleared.diagnostics.emitted_total == before.diagnostics.emitted_total
    assert controller.clear_preview() == cleared

    reused = controller.burst(3)
    assert reused.preview_running is (not paused)
    assert reused.diagnostics is not None
    assert reused.diagnostics.active_or_queued == 3
    assert reused.diagnostics.emitted_total == before.diagnostics.emitted_total + 3
    assert not session.summary().dirty
    assert (root / "config" / "vfx.json").read_bytes() == canonical


@pytest.mark.parametrize("texture", ("/outside/spark.png", r"C:\outside\spark.png"))
def test_vfx_texture_rejects_absolute_project_escape_paths(
    tmp_path: Path,
    texture: str,
) -> None:
    root = new_project21("VFXAbsoluteTexture", "3d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    before = session.vfx.effects()
    with pytest.raises(EditorVFXError22, match="texture must stay project-relative"):
        session.vfx.create_effect("unsafe", backend="gpu3d", texture=texture)
    assert session.vfx.effects() == before
    assert not session.vfx.dirty


def test_integrated_project_missing_gpu_texture_reports_and_blocks_preview(tmp_path: Path) -> None:
    root = new_project21("VFXMissingTexture", "3d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    session.vfx.create_effect(
        "missing-texture",
        backend="gpu3d",
        texture="vfx/missing.png",
    )
    controller = EditorVFXPanelController22(session.vfx)
    controller.select("missing-texture")

    assert controller.frame().messages == ("Missing asset: vfx/missing.png",)
    assert controller.validate() == ("Missing asset: vfx/missing.png",)
    with pytest.raises(ValueError, match="preview blocked by missing assets"):
        controller.start_preview()


def test_integrated_shell_includes_vfx_editor() -> None:
    assert issubclass(TkIntegratedEditorApp21, TkVFXEditorApp22)


def test_nested_texture_symlink_escape_fails_closed(tmp_path: Path) -> None:
    root = new_project21("VFXSymlink", "3d", parent=tmp_path)
    assets = root / "assets"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "spark.png").write_bytes(b"outside")
    link = assets / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable on this runner")

    session = EditorIntegratedProjectSession21.open(root)
    session.vfx.create_effect(
        "unsafe",
        backend="gpu3d",
        texture="linked/spark.png",
    )
    controller = EditorVFXPanelController22(session.vfx)
    frame = controller.select("unsafe")
    assert frame.messages == (
        "VFX asset 'linked/spark.png' resolves outside the project assets directory",
    )
    assert frame.diagnostics is None
    with pytest.raises(ValueError, match="outside"):
        controller.start_preview()
    assert controller.frame().diagnostics is None
    with pytest.raises(ValueError, match="outside"):
        session.vfx.preview("unsafe")
