from swirengine import Rectangle2D, Scene


class Thing:
    def __init__(self):
        self.enabled = True
        self.total = 0.0

    def update(self, dt):
        self.total += dt


def test_scene_add_update_remove():
    scene = Scene()
    item = Thing()
    scene.add(item)
    scene.add(item)
    assert len(scene) == 1
    scene.update(0.5)
    assert item.total == 0.5
    assert scene.remove(item) is True
    assert scene.remove(item) is False
    assert scene.objects == ()


def test_scene_respects_enabled():
    scene = Scene()
    item = Thing()
    item.enabled = False
    scene.add(item)
    scene.update(1.0)
    assert item.total == 0.0


def test_scene_find_and_tags():
    scene = Scene()
    player = Rectangle2D(0, 0, 10, 10, name="player", tags={"hero", "actor"})
    enemy = Rectangle2D(20, 0, 10, 10, name="enemy", tags={"actor"})
    scene.add_many(player, enemy)

    assert scene.find("player") is player
    assert scene.find("missing") is None
    assert scene.tagged("hero") == (player,)
    assert scene.tagged("actor") == (player, enemy)


def test_scene_allows_distinct_equal_objects():
    scene = Scene()
    first = Rectangle2D(0, 0, 10, 10)
    second = Rectangle2D(0, 0, 10, 10)
    assert first == second
    scene.add(first)
    scene.add(second)
    assert len(scene) == 2
    assert scene.objects == (first, second)
