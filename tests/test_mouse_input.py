import glfw

from swirengine.input.manager import InputManager


def test_mouse_button_edges_reset_each_frame() -> None:
    manager = InputManager()
    manager._on_button(0, glfw.PRESS)
    assert manager.mouse_button(0)
    assert manager.mouse_button_pressed(0)

    manager.begin_frame()
    assert manager.mouse_button(0)
    assert not manager.mouse_button_pressed(0)

    manager._on_button(0, glfw.RELEASE)
    assert not manager.mouse_button(0)
    assert manager.mouse_button_released(0)

    manager.begin_frame()
    assert not manager.mouse_button_released(0)
