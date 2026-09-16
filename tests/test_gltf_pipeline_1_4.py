from __future__ import annotations

import json
import struct
from pathlib import Path

from swirengine.asset_pipeline import AssetPipeline
from swirengine.assets import AssetManager
from swirengine.graphics.gltf_pipeline import register_gltf_asset_processor


def _write_external_triangle(tmp_path: Path) -> tuple[Path, Path]:
    payload = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    buffer_path = tmp_path / "mesh.bin"
    buffer_path.write_bytes(payload)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "mesh.bin", "byteLength": len(payload)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(payload)}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }
    source = tmp_path / "triangle.gltf"
    source.write_text(json.dumps(document), encoding="utf-8")
    return source, buffer_path


def test_gltf_processor_imports_and_tracks_external_buffer(tmp_path: Path) -> None:
    source, buffer_path = _write_external_triangle(tmp_path)
    manager = AssetManager(tmp_path)

    with AssetPipeline(manager, max_workers=1) as pipeline:
        name = register_gltf_asset_processor(pipeline)
        assert name == "gltf-primitives"
        result = pipeline.wait(pipeline.submit(source), timeout=2)

        assert result.successful
        assert result.dependencies == (buffer_path.resolve(),)
        assert len(result.value) == 1
        assert result.value[0].mesh.vertex_count == 3
        assert pipeline.cached(source)

        buffer_path.write_bytes(buffer_path.read_bytes()[:-4] + struct.pack("<f", 2.0))
        assert pipeline.cached(source) is False


def test_gltf_processor_supports_custom_registration_name(tmp_path: Path) -> None:
    source, _buffer_path = _write_external_triangle(tmp_path)
    manager = AssetManager(tmp_path)

    with AssetPipeline(manager, max_workers=1) as pipeline:
        assert register_gltf_asset_processor(pipeline, name="scene-gltf") == "scene-gltf"
        assert pipeline.processor_names() == ("scene-gltf",)
        result = pipeline.wait(pipeline.submit(source, processor="scene-gltf"), timeout=2)

    assert result.successful
