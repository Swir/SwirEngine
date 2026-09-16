from __future__ import annotations

import json
from pathlib import Path

from swirengine.graphics.gltf_dependencies import gltf_asset_dependencies


def test_gltf_dependencies_include_external_buffers_and_images(tmp_path: Path) -> None:
    source = tmp_path / "scene.gltf"
    document = {
        "asset": {"version": "2.0"},
        "buffers": [
            {"uri": "mesh.bin", "byteLength": 12},
            {"uri": "data:application/octet-stream;base64,AAAA", "byteLength": 3},
        ],
        "images": [
            {"uri": "textures/albedo.png"},
            {"uri": "data:image/png;base64,AAAA"},
            {"bufferView": 0, "mimeType": "image/png"},
        ],
    }
    source.write_text(json.dumps(document), encoding="utf-8")

    dependencies = gltf_asset_dependencies(source)

    assert dependencies == (
        (tmp_path / "mesh.bin").resolve(),
        (tmp_path / "textures/albedo.png").resolve(),
    )


def test_gltf_dependencies_keep_missing_paths_for_graph_tracking(tmp_path: Path) -> None:
    source = tmp_path / "scene.gltf"
    source.write_text(
        json.dumps(
            {
                "asset": {"version": "2.0"},
                "buffers": [{"uri": "future.bin", "byteLength": 4}],
                "images": [{"uri": "future.png"}],
            }
        ),
        encoding="utf-8",
    )

    dependencies = gltf_asset_dependencies(source)

    assert dependencies == (
        (tmp_path / "future.bin").resolve(),
        (tmp_path / "future.png").resolve(),
    )


def test_glb_without_external_uris_has_no_dependencies(tmp_path: Path) -> None:
    # Minimal GLB: 12-byte header + one padded JSON chunk.
    document = b'{"asset":{"version":"2.0"}}'
    padding = (-len(document)) % 4
    document += b" " * padding
    total = 12 + 8 + len(document)
    payload = (
        b"glTF"
        + (2).to_bytes(4, "little")
        + total.to_bytes(4, "little")
        + len(document).to_bytes(4, "little")
        + (0x4E4F534A).to_bytes(4, "little")
        + document
    )
    source = tmp_path / "embedded.glb"
    source.write_bytes(payload)

    assert gltf_asset_dependencies(source) == ()
