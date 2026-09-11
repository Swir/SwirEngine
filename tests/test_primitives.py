from swirengine import Cube3D, Rectangle2D, Vec3, Color


def test_cube_transform():
    cube = Cube3D(position=Vec3(1, 2, 3), size=2.0)
    assert cube.transform.position == Vec3(1, 2, 3)
    assert cube.transform.scale == Vec3(2, 2, 2)


def test_rectangle_defaults():
    r = Rectangle2D(0, 0, 10, 20)
    assert r.enabled
    assert r.color == Color()
