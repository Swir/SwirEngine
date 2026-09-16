from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from swirengine.asset_optimization import (
    optimize_mesh_data,
    optimize_texture_bytes,
    register_texture_optimizer,
)
from swirengine.asset_pipeline import AssetPipeline
from swirengine.assets import AssetManager
from swirengine.graphics.mesh import MeshData


def _mesh_with_degenerate_triangle() -> MeshData:
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [2.0, 2.0, 2.0],
            [2.0, 2.0, 2.0],
            [2.0, 2.0, 2.0],
        ],
        dtype="f4",
    )
    normals = np.asarray([[0.0, 0.0, 1.0]] * 6, dtype="f4")
    uvs = np.asarray(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [0.2, 0.2],
            [0.2, 0.2],
            [0.2, 0.2],
        ],
        dtype="f4",
    )
    return MeshData(vertices, normals, uvs)


def _png_bytes(size: tuple[int, int] = (64, 32)) -> bytes:
    image = Image.new("RGBA", size, (10, 20, 30, 128))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_mesh_optimizer_removes_degenerate_triangle_and_preserves_attributes() -> None:
    source = _mesh_with_degenerate_triangle()

    result = optimize_mesh_data(source)

    assert result.input_triangles == 2
    assert result.output_triangles == 1
    assert result.removed_degenerate == 1
    assert result.changed is True
    assert result.mesh.vertex_count == 3
    assert result.mesh.has_uvs
    np.testing.assert_array_equal(result.mesh.vertices, source.vertices[:3])
    np.testing.assert_array_equal(result.mesh.normals, source.normals[:3])
    np.testing.assert_array_equal(result.mesh.uvs, source.uvs[:3])


def test_mesh_optimizer_returns_original_mesh_when_nothing_changes() -> None:
    source = MeshData(
        np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype="f4"),
        np.asarray([[0, 0, 1]] * 3, dtype="f4"),
    )

    result = optimize_mesh_data(source)

    assert result.mesh is source
    assert result.changed is False
    assert result.output_triangles == 1


def test_mesh_optimizer_rejects_invalid_or_fully_degenerate_input() -> None:
    source = _mesh_with_degenerate_triangle()
    with pytest.raises(ValueError, match="area_epsilon"):
        optimize_mesh_data(source, area_epsilon=-1)

    degenerate = MeshData(
        np.asarray([[1, 1, 1], [1, 1, 1], [1, 1, 1]], dtype="f4"),
        np.asarray([[0, 1, 0]] * 3, dtype="f4"),
    )
    with pytest.raises(ValueError, match="no non-degenerate"):
        optimize_mesh_data(degenerate)


def test_texture_optimizer_downscales_without_changing_aspect_ratio() -> None:
    payload = _png_bytes((64, 32))

    result = optimize_texture_bytes(payload, max_dimension=16, output_format="PNG")

    assert result.input_size == (64, 32)
    assert result.output_size == (16, 8)
    assert result.changed_dimensions is True
    assert result.input_bytes == len(payload)
    assert result.output_bytes == len(result.data)
    assert result.output_format == "PNG"
    with Image.open(BytesIO(result.data)) as optimized:
        assert optimized.size == (16, 8)
        assert optimized.format == "PNG"


def test_texture_optimizer_never_enlarges_source() -> None:
    result = optimize_texture_bytes(_png_bytes((8, 4)), max_dimension=64)
    assert result.output_size == (8, 4)
    assert result.changed_dimensions is False


def test_texture_optimizer_validates_options() -> None:
    payload = _png_bytes()
    with pytest.raises(ValueError, match="max_dimension"):
        optimize_texture_bytes(payload, max_dimension=0)
    with pytest.raises(ValueError, match="quality"):
        optimize_texture_bytes(payload, quality=101)
    with pytest.raises(ValueError, match="output_format"):
        optimize_texture_bytes(payload, output_format="BMP")


def test_registered_texture_optimizer_runs_in_pipeline_and_caches(tmp_path: Path) -> None:
    source = tmp_path / "hero.png"
    source.write_bytes(_png_bytes((32, 16)))
    manager = AssetManager(tmp_path)

    with AssetPipeline(manager, max_workers=1) as pipeline:
        name = register_texture_optimizer(pipeline, max_dimension=8)
        first = pipeline.wait(pipeline.submit("hero.png"), timeout=2)
        second = pipeline.wait(pipeline.submit("hero.png"), timeout=2)

    assert name == "texture-optimizer"
    assert first.successful and first.cache_hit is False
    assert first.value.output_size == (8, 4)
    assert second.successful and second.cache_hit is True
    assert second.value.output_size == (8, 4)
