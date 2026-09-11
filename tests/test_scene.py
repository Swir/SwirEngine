from swirengine import Scene


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
    assert len(scene.objects) == 1
    scene.update(0.5)
    assert item.total == 0.5
    scene.remove(item)
    assert scene.objects == ()


def test_scene_respects_enabled():
    scene = Scene()
    item = Thing()
    item.enabled = False
    scene.add(item)
    scene.update(1.0)
    assert item.total == 0.0
