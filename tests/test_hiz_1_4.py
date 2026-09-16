from __future__ import annotations

import numpy as np
import pytest

from swirengine.graphics.hiz import HiZDepthPyramid3D


def test_hiz_builds_max_reduction_pyramid() -> None:
    depth = np.asarray(
        [
            [0.2, 0.3, 0.4, 0.5],
            [0.1, 0.6, 0.2, 0.4],
            [0.7, 0.2, 0.8, 0.1],
            [0.3, 0.4, 0.2, 0.9],
        ],
        dtype="f4",
    )
    pyramid = HiZDepthPyramid3D(depth)

    assert pyramid.level_count == 3
    assert pyramid.size == (4, 4)
    assert pyramid.levels[1].tolist() == pytest.approx([[0.6, 0.5], [0.7, 0.9]])
    assert float(pyramid.levels[-1][0, 0]) == pytest.approx(0.9)


def test_hiz_reports_object_behind_solid_occluder_as_occluded() -> None:
    pyramid = HiZDepthPyramid3D(np.full((8, 8), 0.25, dtype="f4"))
    result = pyramid.query_occluded((0.25, 0.25, 0.75, 0.75), 0.8)

    assert result.occluded is True
    assert result.conservative_depth == pytest.approx(0.25)
    assert result.texels_tested >= 1


def test_hiz_hole_prevents_false_positive_occlusion() -> None:
    depth = np.full((8, 8), 0.25, dtype="f4")
    depth[3, 3] = 1.0
    pyramid = HiZDepthPyramid3D(depth)

    result = pyramid.query_occluded((0.25, 0.25, 0.75, 0.75), 0.8)
    assert result.conservative_depth == pytest.approx(1.0)
    assert result.occluded is False


def test_hiz_depth_bias_keeps_near_equal_surface_visible() -> None:
    pyramid = HiZDepthPyramid3D(np.full((4, 4), 0.5, dtype="f4"))

    assert pyramid.query_occluded((0.0, 0.0, 1.0, 1.0), 0.50005, bias=0.001).occluded is False
    assert pyramid.query_occluded((0.0, 0.0, 1.0, 1.0), 0.7, bias=0.001).occluded is True


def test_hiz_validates_depth_and_rectangles() -> None:
    with pytest.raises(ValueError, match="2D"):
        HiZDepthPyramid3D(np.zeros((2, 2, 1), dtype="f4"))
    with pytest.raises(ValueError, match="0..1"):
        HiZDepthPyramid3D(np.asarray([[1.5]], dtype="f4"))

    pyramid = HiZDepthPyramid3D(np.zeros((2, 2), dtype="f4"))
    with pytest.raises(ValueError, match="positive area"):
        pyramid.query_occluded((0.5, 0.5, 0.5, 0.75), 0.5)
    with pytest.raises(ValueError, match="0..1"):
        pyramid.query_occluded((0.0, 0.0, 1.0, 1.0), 1.2)
