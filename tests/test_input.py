from swirengine.input.manager import InputManager


def test_named_key_edges(monkeypatch):
    manager = InputManager()
    monkeypatch.setattr(InputManager, "_named_key", staticmethod(lambda _name: 42))
    manager._keys.add(42)
    manager._pressed.add(42)

    assert manager.key("A")
    assert manager.key_pressed("A")
    assert not manager.key_released("A")

    manager._pressed.clear()
    manager._keys.clear()
    manager._released.add(42)
    assert manager.key_released("A")
