import pytest

from swirengine import Color, Material3D


def test_legacy_phong_material_stays_unchanged():
    material = Material3D(diffuse=0.6, specular=0.2, shininess=24)
    assert material.pbr_enabled is False
    assert material.diffuse == pytest.approx(0.6)
    assert material.specular == pytest.approx(0.2)
    assert material.shininess == pytest.approx(24.0)


def test_metallic_roughness_bridge_keeps_legacy_fields_compatible():
    material = Material3D(diffuse=0.8, metallic=0.75, roughness=0.5)
    assert material.pbr_enabled is True
    assert material.metallic == pytest.approx(0.75)
    assert material.roughness == pytest.approx(0.5)
    assert material.diffuse == pytest.approx(0.2)
    assert material.specular == pytest.approx(0.76)
    assert material.shininess == pytest.approx(30.0)


def test_metallic_roughness_validation_is_strict():
    with pytest.raises(ValueError, match="metallic"):
        Material3D(metallic=1.01)
    with pytest.raises(ValueError, match="roughness"):
        Material3D(roughness=-0.01)


def test_zero_roughness_is_bounded_for_legacy_bridge():
    material = Material3D(metallic=1.0, roughness=0.0)
    assert material.diffuse == pytest.approx(0.0)
    assert material.specular == pytest.approx(1.0)
    assert material.shininess == pytest.approx(256.0)


def test_metallic_roughness_texture_enables_pbr_and_uses_gltf_factor_defaults(tmp_path):
    texture = tmp_path / "mr.png"
    texture.write_bytes(b"not-loaded-by-material")
    material = Material3D(metallic_roughness_texture=texture)

    assert material.pbr_enabled is True
    assert material.metallic == pytest.approx(1.0)
    assert material.roughness == pytest.approx(1.0)
    assert material.metallic_roughness_texture == texture


def test_extended_pbr_maps_are_preserved_without_loading_files(tmp_path):
    normal = tmp_path / "normal.png"
    occlusion = tmp_path / "ao.png"
    emissive = tmp_path / "emissive.png"
    material = Material3D(
        normal_texture=normal,
        normal_scale=0.75,
        occlusion_texture=occlusion,
        occlusion_strength=0.4,
        emissive_texture=emissive,
        emissive_factor=Color(2.0, 0.5, 0.25),
    )

    assert material.pbr_enabled is True
    assert material.normal_texture == normal
    assert material.normal_scale == pytest.approx(0.75)
    assert material.occlusion_texture == occlusion
    assert material.occlusion_strength == pytest.approx(0.4)
    assert material.emissive_texture == emissive
    assert material.emissive_factor == Color(2.0, 0.5, 0.25)
    assert material.metallic == pytest.approx(0.0)
    assert material.roughness == pytest.approx(0.5)


def test_extended_pbr_controls_validate_ranges():
    with pytest.raises(ValueError, match="normal_scale"):
        Material3D(normal_scale=-0.01)
    with pytest.raises(ValueError, match="occlusion_strength"):
        Material3D(occlusion_strength=1.01)
    with pytest.raises(ValueError, match="emissive_factor"):
        Material3D(emissive_factor=Color(-0.01, 0.0, 0.0))


def test_non_black_emissive_factor_enables_pbr():
    material = Material3D(emissive_factor=Color(0.1, 0.0, 0.0))

    assert material.pbr_enabled is True
    assert material.metallic == pytest.approx(0.0)
    assert material.roughness == pytest.approx(0.5)
