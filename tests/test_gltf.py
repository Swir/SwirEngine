import base64
import json
import struct

import numpy as np
import pytest

from swirengine import Game, load_gltf


def _triangle_payload() -> bytes:
    positions = struct.pack(
        "<9f",
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
    )
    uvs = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
    indices = struct.pack("<3H", 0, 1, 2)
    return positions + uvs + indices


def _document(buffer_uri: str, byte_length: int) -> dict:
    return {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": buffer_uri, "byteLength": byte_length}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 24},
            {"buffer": 0, "byteOffset": 60, "byteLength": 6},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"},
            {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "TEXCOORD_0": 1},
                        "indices": 2,
                    }
                ]
            }
        ],
    }


def test_load_gltf_external_buffer_and_generate_normals(tmp_path):
    payload = _triangle_payload()
    (tmp_path / "mesh.bin").write_bytes(payload)
    path = tmp_path / "mesh.gltf"
    path.write_text(json.dumps(_document("mesh.bin", len(payload))), encoding="utf-8")

    mesh = load_gltf(path)

    assert mesh.vertex_count == 3
    assert mesh.has_uvs
    assert mesh.uvs is not None
    assert np.allclose(mesh.uvs, ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)))
    assert np.allclose(mesh.normals, (0.0, 0.0, 1.0))


def test_load_gltf_supports_base64_data_uri(tmp_path):
    payload = _triangle_payload()
    encoded = base64.b64encode(payload).decode("ascii")
    document = _document(f"data:application/octet-stream;base64,{encoded}", len(payload))
    path = tmp_path / "embedded.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")

    mesh = load_gltf(path)

    assert mesh.triangle_count == 1
    assert np.allclose(mesh.vertices[1], (1.0, 0.0, 0.0))


def test_load_gltf_rejects_non_triangle_mode(tmp_path):
    payload = _triangle_payload()
    encoded = base64.b64encode(payload).decode("ascii")
    document = _document(f"data:application/octet-stream;base64,{encoded}", len(payload))
    document["meshes"][0]["primitives"][0]["mode"] = 5
    path = tmp_path / "strip.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="TRIANGLES"):
        load_gltf(path)


def test_load_gltf_rejects_glb_until_binary_container_support_exists(tmp_path):
    path = tmp_path / "mesh.glb"
    path.write_bytes(b"glTF")
    with pytest.raises(ValueError, match="GLB"):
        load_gltf(path)


def test_game_gltf_requires_3d_mode(tmp_path):
    game = Game(asset_root=tmp_path)
    with pytest.raises(RuntimeError, match="mode='3d'"):
        game.gltf("mesh.gltf")
