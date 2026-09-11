import math

import numpy as np

from swirengine import Color, Transform, Vec2, Vec3


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
