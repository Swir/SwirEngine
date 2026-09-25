from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_vfx22 import MAX_VFX_PREVIEW_STEP, EditorVFXPanelController22
from swirengine.gpu_particles import GPUParticleEmitter3D
from swirengine.particles import ParticleEmitter2D
from swirengine.project_scaffold21 import new_project21
from swirengine.vfx_authoring22 import EditorVFXTooling22
from swirengine.vfx_schema22 import EditorVFXError22


def test_vfx_library_round_trips_cpu_runtime_deterministically(tmp_path: Path) -> None:
    tooling = EditorVFXTooling22(tmp_path)
    tooling.create_effect(
        "dust",
        backend="cpu2d",
        capacity=96,
        rate=14.0,
        emission_shape="box",
        emission_extent=(8.0, 4.0, 0.0),
        start_color=(0.8, 0.7, 0.5, 1.0),
        end_color=(0.6, 0.5, 0.4, 0.0),
    )
    tooling.save()
    first = tooling.target.read_text(encoding="utf-8")
    runtime = tooling.build_runtime("dust")
    assert isinstance(runtime, ParticleEmitter2D)
    assert runtime.max_particles == 96
    assert runtime.rate == pytest.approx(14.0)

    reopened = EditorVFXTooling22(tmp_path)
    assert reopened.effects() == tooling.effects()
    reopened.save()
    assert reopened.target.read_text(encoding="utf-8") == first


def test_vfx_gpu_preview_uses_shipping_runtime_and_project_texture(tmp_path: Path) -> None:
    texture = tmp_path / "assets" / "vfx" / "spark.png"
    texture.parent.mkdir(parents=True)
    texture.write_bytes(b"fixture")
    tooling = EditorVFXTooling22(tmp_path)
    tooling.create_effect(
        "sparks",
        backend="gpu3d",
        capacity=2048,
        rate=300.0,
        emission_shape="sphere",
        emission_extent=(0.5, 0.5, 0.5),
        texture="vfx/spark.png",
    )
    preview = tooling.preview("sparks")
    assert isinstance(preview.runtime, GPUParticleEmitter3D)
    assert preview.runtime.capacity == 2048
    assert preview.runtime.texture == str(texture.resolve())
    assert preview.missing_assets == ()
    assert len(preview.fingerprint) == 64


def test_vfx_paths_reject_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(EditorVFXError22, match="project-relative"):
        EditorVFXTooling22(tmp_path, path="../vfx.json")

    tooling = EditorVFXTooling22(tmp_path)
    with pytest.raises(EditorVFXError22, match="project-relative"):
        tooling.create_effect("escape", backend="gpu3d", texture="../outside.png")


def test_vfx_controller_presets_and_bounded_preview(tmp_path: Path) -> None:
    controller = EditorVFXPanelController22(EditorVFXTooling22(tmp_path))
    frame = controller.create("smoke", preset="soft-smoke-2d")
    assert frame.backend == "cpu2d"
    assert controller.start_preview().preview_running
    controller.burst(12)
    frame = controller.step_preview(1.0)
    assert frame.diagnostics is not None
    assert frame.diagnostics.last_step == pytest.approx(MAX_VFX_PREVIEW_STEP)
    assert frame.diagnostics.step_was_clamped
    assert frame.diagnostics.emitted_total >= 12

    controller.apply_preset("fire-gpu")
    frame = controller.start_preview()
    assert frame.backend == "gpu3d"
    controller.burst(20)
    frame = controller.step_preview(1.0 / 60.0)
    assert frame.diagnostics is not None
    assert frame.diagnostics.capacity == 8192


def test_integrated_session_saves_and_reopens_vfx_library(tmp_path: Path) -> None:
    root = new_project21("VFXIntegrated", "3d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    session.vfx.create_effect("impact", backend="gpu3d", rate=80.0)
    assert session.summary().dirty
    session.save()
    assert not session.vfx.dirty
    assert (root / "config" / "vfx.json").is_file()

    reopened = EditorIntegratedProjectSession21.open(root)
    assert tuple(item.name for item in reopened.vfx.effects()) == ("impact",)
    assert not reopened.summary().dirty
