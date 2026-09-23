from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_material_tooling22 import (
    EditorMaterialTooling22,
    EditorMaterialToolingError,
)


def test_material_library_round_trips_deterministically(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)
    (tmp_path / "assets" / "textures").mkdir(parents=True)
    (tmp_path / "assets" / "textures" / "panel.png").write_bytes(b"swir-material-fixture")

    tooling.create_material(
        "panel",
        texture="textures/panel.png",
        metallic=0.2,
        roughness=0.65,
        normal_scale=0.8,
        shader_defines=(("USE_DETAIL", True),),
        shader_hooks=(("fragment_surface", "surface_rgba.rgb *= 0.75;"),),
        shader_uniforms=(("creator_gain", 0.75),),
        strict_uniforms=False,
    )
    assert tooling.dirty is True

    saved = tooling.save()
    first = (tmp_path / "config" / "materials.json").read_text(encoding="utf-8")
    assert saved.dirty is False

    reopened = EditorMaterialTooling22(tmp_path)
    assert reopened.snapshot().materials == saved.materials
    reopened.save()
    assert (tmp_path / "config" / "materials.json").read_text(encoding="utf-8") == first
    payload = json.loads(first)
    assert payload["format"] == "swirengine.material-library"
    assert payload["version"] == 1


def test_material_preview_uses_shipping_runtime_types_and_shader_contract(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)
    (tmp_path / "assets" / "textures").mkdir(parents=True)
    texture = tmp_path / "assets" / "textures" / "metal.png"
    texture.write_bytes(b"swir-material")

    tooling.create_material(
        "metal",
        texture="textures/metal.png",
        tint=(0.8, 0.9, 1.0, 1.0),
        metallic=0.9,
        roughness=0.15,
        emissive_factor=(0.1, 0.2, 0.3, 1.0),
        shader_hooks=(("fragment_surface", "surface_rgba.rgb *= 0.9;"),),
        shader_uniforms=(("gain", (1.0, 0.5, 0.25)),),
        strict_uniforms=False,
    )

    preview = tooling.preview("metal")

    assert preview.material.texture == texture.resolve()
    assert preview.material.pbr_enabled is True
    assert preview.material.metallic == pytest.approx(0.9)
    assert preview.material.roughness == pytest.approx(0.15)
    assert preview.shader_material is not None
    assert preview.shader_material.variant.template_name == "swir_surface_3d"
    assert preview.shader_material.uniforms["gain"] == (1.0, 0.5, 0.25)
    assert preview.missing_assets == ()
    assert len(preview.fingerprint) == 64


def test_material_tooling_reports_missing_assets_and_blocks_path_escape(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)
    tooling.create_material("missing", normal_texture="textures/missing-normal.png")

    assert tooling.missing_assets("missing") == ("textures/missing-normal.png",)

    with pytest.raises(EditorMaterialToolingError, match="assets directory"):
        tooling.create_material("escape", texture="../secret.png")
    with pytest.raises(EditorMaterialToolingError, match="project-relative"):
        EditorMaterialTooling22(tmp_path, path="../materials.json")


def test_material_shader_authoring_reuses_shipping_safety_policy(tmp_path: Path) -> None:
    tooling = EditorMaterialTooling22(tmp_path)

    with pytest.raises(EditorMaterialToolingError, match="blocked token"):
        tooling.create_material(
            "unsafe",
            shader_hooks=(("fragment_surface", "gl_FragDepth = 0.0;"),),
        )

    with pytest.raises(EditorMaterialToolingError, match="invalid shader define"):
        tooling.create_material(
            "bad-define",
            shader_defines=(("BAD-NAME", 1),),
        )


def test_integrated_session_marks_material_changes_dirty_and_reopens(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("MaterialSession", "3d")
    session = EditorIntegratedProjectSession21.open(root)

    session.materials.create_material("hero", metallic=0.6, roughness=0.3)

    assert session.summary().dirty is True
    session.save()
    assert session.summary().dirty is False
    assert (root / "config" / "materials.json").is_file()

    reopened = EditorIntegratedProjectSession21.open(root)
    materials = reopened.materials.snapshot().materials
    assert tuple(item.name for item in materials) == ("hero",)
    assert materials[0].metallic == pytest.approx(0.6)
    assert reopened.summary().dirty is False


def test_project_hub_session_can_be_promoted_with_material_tooling(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("MaterialPromoted", "3d")
    base = EditorProjectSession.open(root)

    promoted = EditorIntegratedProjectSession21.adopt(base)

    assert promoted.controller is base.controller
    assert promoted.workspace is base.workspace
    assert promoted.materials.project_root == root.resolve()
