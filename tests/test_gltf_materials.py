import base64
import json
import struct

import pytest

from swirengine import load_gltf_material, load_gltf_primitives

_PIXEL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _write_asset(tmp_path, *, alpha_mode="OPAQUE"):
    vertices = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    uvs = struct.pack("<6f", 0, 0, 1, 0, 0, 1)
    payload = vertices + uvs
    document = {
        "asset": {"version": "2.0"},
        "buffers": [
            {
                "byteLength": len(payload),
                "uri": "data:application/octet-stream;base64,"
                + base64.b64encode(payload).decode("ascii"),
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vertices)},
            {"buffer": 0, "byteOffset": len(vertices), "byteLength": len(uvs)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"},
        ],
        "images": [
            {"uri": "data:image/png;base64," + _PIXEL_PNG}
        ],
        "textures": [{"source": 0}],
        "materials": [
            {
                "alphaMode": alpha_mode,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.25, 0.5, 0.75, 1.0],
                    "baseColorTexture": {"index": 0},
                    "metallicFactor": 0.2,
                    "roughnessFactor": 0.7,
                },
            }
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "TEXCOORD_0": 1},
                        "material": 0,
                    }
                ]
            }
        ],
    }
    path = tmp_path / "material.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_gltf_primitives_preserve_material_and_uvs(tmp_path):
    path = _write_asset(tmp_path)
    assets = load_gltf_primitives(path)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.primitive_index == 0
    assert asset.material_index == 0
    assert asset.mesh.has_uvs
    assert asset.metallic_factor == pytest.approx(0.2)
    assert asset.roughness_factor == pytest.approx(0.7)
    assert asset.material.tint.r == pytest.approx(0.25)
    assert asset.material.tint.g == pytest.approx(0.5)
    assert asset.material.tint.b == pytest.approx(0.75)
    assert asset.material.texture is not None
    assert asset.material.texture.is_file()
    assert asset.material.texture.read_bytes() == base64.b64decode(_PIXEL_PNG)


def test_load_gltf_material_reuses_renderer_ready_texture_path(tmp_path):
    path = _write_asset(tmp_path)
    first = load_gltf_material(path)
    second = load_gltf_material(path)
    assert first.texture == second.texture
    assert first.texture is not None and first.texture.suffix == ".png"


def test_non_opaque_gltf_material_fails_explicitly(tmp_path):
    path = _write_asset(tmp_path, alpha_mode="BLEND")
    with pytest.raises(ValueError, match="alphaMode"):
        load_gltf_primitives(path)
