from swirengine import Camera2D, Color, Cube3D, Rectangle2D, Sprite2D, Vec3


def test_cube_transform():
    cube = Cube3D(position=Vec3(1, 2, 3), size=2.0)
    transform = cube.transform
    assert transform.position == Vec3(1, 2, 3)
    assert transform.scale == Vec3(2, 2, 2)


def test_rectangle_defaults():
    rectangle = Rectangle2D(0, 0, 10, 20)
    assert rectangle.enabled
    assert rectangle.visible
    assert rectangle.color == Color()


def test_sprite_defaults():
    sprite = Sprite2D("player.png", x=10, y=20, name="player")
    assert sprite.texture == "player.png"
    assert sprite.width is None
    assert sprite.height is None
    assert sprite.tint == Color()
    assert sprite.name == "player"


def test_camera_helpers():
    sprite = Sprite2D("player.png", x=15, y=-7)
    camera = Camera2D(zoom=0)
    assert camera.safe_zoom == 0.001
    camera.follow(sprite)
    assert (camera.x, camera.y) == (15, -7)
    camera.move(5, 2)
    assert (camera.x, camera.y) == (20, -5)
