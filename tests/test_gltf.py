import base64
import json
import struct

import numpy as np
import pytest

from swirengine import Game, load_gltf, load_gltf_scene


def _triangle_payload() -> bytes:
    positions = struct.pack(
        "<9f",
        0.0, 0.0, 0.0,
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
    )
    uvs = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
    indices = struct.pack("<3H", 0, 1, 2)
    return positions + uvs + indices


def _document(buffer_uri: str | None, byte_length: int) -> dict:
    buffer = {"byteLength": byte_length}
    if buffer_uri is not None:
        buffer["uri"] = buffer_uri
    return {
        "asset": {"version": "2.0"},
        "buffers": [buffer],
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
            {"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2}]}
        ],
    }


def _write_glb(path, document: dict, binary: bytes) -> None:
    json_payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_payload += b" " * ((4 - len(json_payload) % 4) % 4)
    binary_payload = binary + b"\x00" * ((4 - len(binary) % 4) % 4)
    total = 12 + 8 + len(json_payload) + 8 + len(binary_payload)
    payload = bytearray(struct.pack("<4sII", b"glTF", 2, total))
    payload.extend(struct.pack("<II", len(json_payload), 0x4E4F534A))
    payload.extend(json_payload)
    payload.extend(struct.pack("<II", len(binary_payload), 0x004E4942))
    payload.extend(binary_payload)
    path.write_bytes(payload)


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
    path = tmp_path / "embedded.gltf"
    path.write_text(
        json.dumps(_document(f"data:application/octet-stream;base64,{encoded}", len(payload))),
        encoding="utf-8",
    )
    mesh = load_gltf(path)
    assert mesh.triangle_count == 1
    assert np.allclose(mesh.vertices[1], (1.0, 0.0, 0.0))


def test_load_gltf_supports_glb_binary_chunk(tmp_path):
    payload = _triangle_payload()
    path = tmp_path / "mesh.glb"
    _write_glb(path, _document(None, len(payload)), payload)
    mesh = load_gltf(path)
    assert mesh.vertex_count == 3
    assert mesh.has_uvs
    assert np.allclose(mesh.vertices[2], (0.0, 1.0, 0.0))


def test_load_gltf_scene_applies_hierarchical_trs(tmp_path):
    payload = _triangle_payload()
    encoded = base64.b64encode(payload).decode("ascii")
    document = _document(f"data:application/octet-stream;base64,{encoded}", len(payload))
    document["nodes"] = [
        {"translation": [10, 0, 0], "children": [1]},
        {"name": "triangle", "mesh": 0, "translation": [0, 2, 0], "scale": [2, 2, 2]},
    ]
    document["scenes"] = [{"nodes": [0]}]
    document["scene"] = 0
    path = tmp_path / "scene.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")

    instances = load_gltf_scene(path)

    assert len(instances) == 1
    assert instances[0].node_name == "triangle"
    assert instances[0].node_index == 1
    assert np.allclose(instances[0].mesh.vertices[0], (10.0, 2.0, 0.0))
    assert np.allclose(instances[0].mesh.vertices[1], (12.0, 2.0, 0.0))


def test_load_gltf_scene_applies_quaternion_rotation(tmp_path):
    payload = _triangle_payload()
    encoded = base64.b64encode(payload).decode("ascii")
    document = _document(f"data:application/octet-stream;base64,{encoded}", len(payload))
    s = 2**-0.5
    document["nodes"] = [{"mesh": 0, "rotation": [0, 0, s, s]}]
    document["scenes"] = [{"nodes": [0]}]
    path = tmp_path / "rotated.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")

    mesh = load_gltf_scene(path)[0].mesh

    assert np.allclose(mesh.vertices[1], (0.0, 1.0, 0.0), atol=1e-6)
    assert np.allclose(mesh.normals, (0.0, 0.0, 1.0), atol=1e-6)


def test_load_gltf_scene_rejects_cycles(tmp_path):
    payload = _triangle_payload()
    encoded = base64.b64encode(payload).decode("ascii")
    document = _document(f"data:application/octet-stream;base64,{encoded}", len(payload))
    document["nodes"] = [{"children": [1]}, {"mesh": 0, "children": [0]}]
    document["scenes"] = [{"nodes": [0]}]
    path = tmp_path / "cycle.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="cycle"):
        load_gltf_scene(path)


def test_load_gltf_rejects_non_triangle_mode(tmp_path):
    payload = _triangle_payload()
    encoded = base64.b64encode(payload).decode("ascii")
    document = _document(f"data:application/octet-stream;base64,{encoded}", len(payload))
    document["meshes"][0]["primitives"][0]["mode"] = 5
    path = tmp_path / "strip.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="TRIANGLES"):
        load_gltf(path)


def test_load_gltf_rejects_malformed_glb(tmp_path):
    path = tmp_path / "mesh.glb"
    path.write_bytes(b"glTF")
    with pytest.raises(ValueError, match="header"):
        load_gltf(path)


def test_game_gltf_requires_3d_mode(tmp_path):
    game = Game(asset_root=tmp_path)
    with pytest.raises(RuntimeError, match="mode='3d'"):
        game.gltf("mesh.gltf")
