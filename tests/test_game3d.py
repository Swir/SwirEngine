import numpy as np
import pytest

from swirengine import Camera2D, Camera3D, Game, MeshData


def test_game_selects_camera_for_mode():
    assert isinstance(Game(mode="2d").camera, Camera2D)
    assert isinstance(Game(mode="3d").camera, Camera3D)


def test_mesh_factory_is_3d_only():
    data = MeshData(
        np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype="f4"),
        np.asarray(((0, 0, 1), (0, 0, 1), (0, 0, 1)), dtype="f4"),
    )
    with pytest.raises(RuntimeError, match="mode='3d'"):
        Game().mesh(data)
    assert Game(mode="3d").mesh(data).mesh is data
