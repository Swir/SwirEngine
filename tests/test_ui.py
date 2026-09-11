from swirengine import Game, UIButton, UIManager, UIProgressBar
from swirengine.core.scene import Scene


class FakeInput:
    def __init__(self) -> None:
        self.mouse_x = 0.0
        self.mouse_y = 0.0
        self.held = False
        self.pressed = False
        self.released = False

    def mouse_button(self, button: int) -> bool:
        return button == 0 and self.held

    def mouse_button_pressed(self, button: int) -> bool:
        return button == 0 and self.pressed

    def mouse_button_released(self, button: int) -> bool:
        return button == 0 and self.released


def test_ui_manager_registers_screen_space_children() -> None:
    scene = Scene()
    ui = UIManager(scene)
    label = ui.label("Score", 10, 20)
    panel = ui.panel(0, 0, 300, 180)

    assert label.text_object in scene
    assert panel.background in scene
    assert label.text_object.screen_space
    assert panel.background.screen_space


def test_button_click_requires_press_and_release_inside() -> None:
    scene = Scene()
    ui = UIManager(scene)
    clicks: list[str] = []
    button = ui.button("Play", 0, 0, on_click=lambda item: clicks.append(item.text))
    pointer = FakeInput()
    pointer.mouse_x = 400
    pointer.mouse_y = 300

    pointer.pressed = True
    pointer.held = True
    ui.update(pointer, 800, 600)
    assert button.pressed
    assert button.hovered

    pointer.pressed = False
    pointer.held = False
    pointer.released = True
    ui.update(pointer, 800, 600)
    assert clicks == ["Play"]
    assert not button.pressed


def test_button_release_outside_does_not_click() -> None:
    ui = UIManager(Scene())
    clicks: list[int] = []
    ui.button("Play", 0, 0, on_click=lambda _item: clicks.append(1))
    pointer = FakeInput()
    pointer.mouse_x = 400
    pointer.mouse_y = 300
    pointer.pressed = True
    pointer.held = True
    ui.update(pointer, 800, 600)

    pointer.pressed = False
    pointer.held = False
    pointer.released = True
    pointer.mouse_x = 799
    pointer.mouse_y = 599
    ui.update(pointer, 800, 600)
    assert clicks == []


def test_overlapping_buttons_only_hover_topmost() -> None:
    ui = UIManager(Scene())
    lower = ui.add(UIButton("Lower", 0, 0))
    upper = ui.add(UIButton("Upper", 0, 0))
    pointer = FakeInput()
    pointer.mouse_x = 400
    pointer.mouse_y = 300

    ui.update(pointer, 800, 600)
    assert upper.hovered
    assert not lower.hovered


def test_progress_bar_clamps_and_updates_fill_geometry() -> None:
    bar = UIProgressBar(0, 0, width=200, value=0.25)
    assert bar.value == 0.25
    assert bar.fill.width == 50
    assert bar.fill.x == -75

    bar.value = 2
    assert bar.value == 1.0
    assert bar.fill.width == 200
    assert bar.fill.visible

    bar.value = -1
    assert bar.value == 0.0
    assert not bar.fill.visible


def test_game_ui_factories_and_cleanup() -> None:
    game = Game()
    button = game.button("Quit", 0, 0)
    label = game.label("HUD", 0, 100)
    bar = game.progress_bar(0, 50, value=0.5)

    assert button in game.ui.controls
    assert label in game.ui.controls
    assert bar in game.ui.controls
    assert game.remove(button)
    assert button not in game.ui.controls
    assert button.background not in game.scene
    assert button.label not in game.scene


def test_world_text_factory_is_not_screen_space() -> None:
    game = Game()
    text = game.text("Hello", 12, 34)
    assert text.text == "Hello"
    assert not text.screen_space
    assert text in game.scene
