import math

import numpy as np

from swirengine import Color, Transform, Vec2, Vec3
from swirengine.math.types import _cached_transform_matrix


def test_vec2_length_and_normalize():
    vector = Vec2(3, 4)
    assert vector.length == 5
    assert math.isclose(vector.normalized().length, 1.0)


def test_vec3_ops():
    assert Vec3(1, 2, 3) + Vec3(3, 2, 1) == Vec3(4, 4, 4)
    assert 2 * Vec3(1, 2, 3) == Vec3(2, 4, 6)


def test_color_clamp():
    assert Color(-1, 0.5, 2, 3).clamped() == Color(0, 0.5, 1, 1)


def test_transform_translation():
    matrix = Transform(position=Vec3(1, 2, 3)).matrix()
    assert np.allclose(matrix[:3, 3], [1, 2, 3])


def test_repeated_transform_matrix_uses_bounded_cache():
    _cached_transform_matrix.cache_clear()
    transform = Transform(
        position=Vec3(1, 2, 3),
        rotation=Vec3(10, 20, 30),
        scale=Vec3(2, 3, 4),
    )

    first = transform.matrix()
    after_first = _cached_transform_matrix.cache_info()
    second = transform.matrix()
    after_second = _cached_transform_matrix.cache_info()

    assert np.allclose(first, second)
    assert after_first.misses == 1
    assert after_second.misses == 1
    assert after_second.hits == 1
    assert after_second.maxsize == 8192


def test_transform_cache_does_not_share_mutable_result_arrays():
    transform = Transform(position=Vec3(4, 5, 6))
    first = transform.matrix()
    first[0, 3] = 999.0

    second = transform.matrix()

    assert second[0, 3] == 4.0
    assert second[0, 3] != first[0, 3]


def test_transform_cache_invalidates_naturally_when_values_change():
    _cached_transform_matrix.cache_clear()
    transform = Transform(position=Vec3(1, 0, 0))
    first = transform.matrix()
    transform.position.x = 2
    second = transform.matrix()

    assert first[0, 3] == 1.0
    assert second[0, 3] == 2.0
    assert _cached_transform_matrix.cache_info().misses == 2
