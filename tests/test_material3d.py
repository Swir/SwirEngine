import pytest

from swirengine import Material3D


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
