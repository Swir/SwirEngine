import numpy as np
import pytest

from swirengine import Camera3D, Vec3


def test_default_camera_view_is_identity():
    camera = Camera3D()
    assert np.allclose(camera.view_matrix(), np.eye(4, dtype="f4"))


def test_camera_local_movement_preserves_view_direction():
    camera = Camera3D()
    camera.move_local(forward=2.0, right=1.0, up=0.5)
    assert camera.position == Vec3(1.0, 0.5, -2.0)
    assert camera.forward == Vec3(0.0, 0.0, -1.0)


def test_camera_rejects_degenerate_look_at():
    camera = Camera3D(target=Vec3())
    with pytest.raises(ValueError, match="different"):
        camera.view_matrix()
