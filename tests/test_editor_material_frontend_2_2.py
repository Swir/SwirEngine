from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.editor_asset_app21 import TkIntegratedEditorApp21
from swirengine.editor_material_frontend22 import (
    EditorMaterialPanelController22,
    TkMaterialEditorApp22,
)
from swirengine.editor_material_tooling22 import (
    EditorMaterialTooling22,
    EditorMaterialToolingError,
)
from swirengine.editor_preview import EditorViewportImage
from swirengine.graphics.lights import DirectionalLight3D
from swirengine.graphics.mesh import Mesh3D
from swirengine.graphics.shader_mesh import ShaderMesh3D


class _FakeViewport:
    def __init__(self) -> None:
        self.calls: list[tuple[object, int, int, object, str | None]] = []

    def capture(
        self,
        scene: object,
        width: int,
        height: int,
        *,
        camera: object | None = None,
        mode: str | None = None,
    ) -> EditorViewportImage:
        self.calls.append((scene, width, height, camera, mode))
        return EditorViewportImage(width, height, b"\x00" * (width * height * 3))


def test_material_panel_creator_workflow_and_presets(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)
    controller = EditorMaterialPanelController22(tooling)

    controller.create("hero", preset="metal")
    spec = controller.selected_spec()
    assert spec.metallic == pytest.approx(1.0)
    assert spec.roughness == pytest.approx(0.18)

    controller.update_surface(
        tint=(0.4, 0.6, 0.9, 1.0),
        roughness=0.28,
        double_sided=True,
    )
    controller.set_texture("normal", "textures/hero-normal.png")
    frame = controller.frame()
    assert frame.selected == "hero"
    assert frame.dirty is True
    assert frame.missing_assets == ("textures/hero-normal.png",)

    texture = tmp_path / "assets" / "textures" / "hero-normal.png"
    texture.parent.mkdir(parents=True)
    texture.write_bytes(b"fixture")
    assert controller.frame().missing_assets == ()

    controller.duplicate("hero_alt")
    assert controller.frame().selected == "hero_alt"
    controller.apply_preset("matte")
    assert controller.selected_spec().roughness == pytest.approx(0.85)
    controller.remove()
    assert controller.frame().material_names == ("hero",)


def test_material_panel_shader_edits_reuse_runtime_validation(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)
    controller = EditorMaterialPanelController22(tooling)
    controller.create("shader")
    controller.update_surface(strict_uniforms=False)

    controller.set_shader_define("USE_DETAIL", True)
    controller.set_shader_hook(
        "fragment_surface",
        "surface_rgba.rgb *= 0.75;",
    )
    controller.set_shader_uniform("creator_gain", [1.0, 0.5, 0.25])

    spec = controller.selected_spec()
    assert spec.shader_defines == (("USE_DETAIL", True),)
    assert spec.shader_hooks == (("fragment_surface", "surface_rgba.rgb *= 0.75;"),)
    assert spec.shader_uniforms == (("creator_gain", (1.0, 0.5, 0.25)),)
    assert any("shipping swir_surface_3d" in item for item in controller.validate())

    with pytest.raises(EditorMaterialToolingError, match="blocked token"):
        controller.set_shader_hook("fragment_surface", "gl_FragDepth = 0.0;")


def test_live_preview_uses_shipping_mesh_and_shader_paths(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)
    controller = EditorMaterialPanelController22(tooling)
    viewport = _FakeViewport()

    controller.create("standard", preset="metal")
    standard = controller.render_preview(viewport, width=160, height=96)
    standard_scene = viewport.calls[-1][0]
    assert standard.scene_object_type == "Mesh3D"
    assert standard.shader_enabled is False
    assert any(isinstance(obj, Mesh3D) for obj in standard_scene.objects)
    assert any(isinstance(obj, DirectionalLight3D) for obj in standard_scene.objects)
    assert viewport.calls[-1][4] == "3d"

    controller.create("shader")
    controller.update_surface(strict_uniforms=False)
    controller.set_shader_hook(
        "fragment_surface",
        "surface_rgba.rgb = pow(surface_rgba.rgb, vec3(0.9));",
    )
    shader = controller.render_preview(viewport, width=160, height=96)
    shader_scene = viewport.calls[-1][0]
    assert shader.scene_object_type == "ShaderMesh3D"
    assert shader.shader_enabled is True
    assert any(isinstance(obj, ShaderMesh3D) for obj in shader_scene.objects)
    assert shader.image is not None
    assert shader.image.width == 160
    assert shader.image.height == 96


def test_live_preview_fails_closed_on_missing_assets(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)
    controller = EditorMaterialPanelController22(tooling)
    viewport = _FakeViewport()

    controller.create("broken")
    controller.set_texture("emissive", "textures/missing.png")
    result = controller.render_preview(viewport)

    assert result.image is None
    assert result.scene_object_type == "none"
    assert result.diagnostics == ("Missing asset: textures/missing.png",)
    assert viewport.calls == []


def test_material_controller_rejects_unknown_editor_fields_and_slots(tmp_path: Path) -> None:
    controller = EditorMaterialPanelController22(EditorMaterialTooling22(tmp_path))
    controller.create("guarded")

    with pytest.raises(EditorMaterialToolingError, match="unsupported surface"):
        controller.update_surface(renderer_secret=True)
    with pytest.raises(EditorMaterialToolingError, match="texture slot"):
        controller.set_texture("unsafe", "x.png")
    with pytest.raises(EditorMaterialToolingError, match="shader hook"):
        controller.set_shader_hook("main", "surface_rgba *= 0.5;")


def test_integrated_editor_shell_includes_material_editor() -> None:
    assert issubclass(TkIntegratedEditorApp21, TkMaterialEditorApp22)
