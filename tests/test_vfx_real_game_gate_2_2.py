from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.editor_asset_app21 import TkIntegratedEditorApp21
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_vfx22 import EditorVFXPanelController22
from swirengine.editor_vfx_frontend22 import TkVFXEditorApp22
from swirengine.gpu_particles import GPUParticleEmitter3D
from swirengine.particles import ParticleEmitter2D
from swirengine.project_scaffold21 import new_project21


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
    runtime_type: type[ParticleEmitter2D] | type[GPUParticleEmitter3D],
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

    reopened.vfx.save()
    assert (root / "config" / "vfx.json").read_bytes() == canonical


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
    with pytest.raises(ValueError, match="outside"):
        session.vfx.preview("unsafe")
