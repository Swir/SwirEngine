from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from .core.scene import Scene
from .graphics.primitives import Rectangle2D, Text2D
from .input.manager import InputManager
from .math.types import Color

if TYPE_CHECKING:
    from .ui_layout import UIContainer, UILayout
    from .ui_navigation import UIFocusManager

T = TypeVar("T")


def _color_or(value: Color | None, default: tuple[float, float, float, float]) -> Color:
    return value if value is not None else Color(*default)


class UILabel:
    def __init__(
        self,
        text: str,
        x: float = 0.0,
        y: float = 0.0,
        *,
        color: Color | None = None,
        font_size: int = 24,
        font: str | None = None,
        scale: float = 1.0,
        layer: int = 1000,
    ) -> None:
        self.text_object = Text2D(
            text,
            x,
            y,
            _color_or(color, (1.0, 1.0, 1.0, 1.0)),
            font_size=font_size,
            font=font,
            scale=scale,
            layer=layer,
            screen_space=True,
        )

    @property
    def children(self) -> tuple[object, ...]:
        return (self.text_object,)

    @property
    def text(self) -> str:
        return self.text_object.text

    @text.setter
    def text(self, value: str) -> None:
        self.text_object.text = str(value)

    @property
    def x(self) -> float:
        return self.text_object.x

    @x.setter
    def x(self, value: float) -> None:
        self.text_object.x = float(value)

    @property
    def y(self) -> float:
        return self.text_object.y

    @y.setter
    def y(self, value: float) -> None:
        self.text_object.y = float(value)


class UIPanel:
    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        color: Color | None = None,
        layer: int = 900,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.width = max(1.0, float(width))
        self.height = max(1.0, float(height))
        self.background = Rectangle2D(
            self.x,
            self.y,
            self.width,
            self.height,
            _color_or(color, (0.08, 0.10, 0.16, 0.94)),
            layer=layer,
            screen_space=True,
        )

    @property
    def children(self) -> tuple[object, ...]:
        return (self.background,)

    def _sync(self) -> None:
        self.background.x = self.x
        self.background.y = self.y
        self.background.width = self.width
        self.background.height = self.height


class UIButton:
    def __init__(
        self,
        text: str,
        x: float,
        y: float,
        width: float = 220.0,
        height: float = 56.0,
        *,
        on_click: Callable[[UIButton], None] | None = None,
        color: Color | None = None,
        hover_color: Color | None = None,
        pressed_color: Color | None = None,
        focused_color: Color | None = None,
        text_color: Color | None = None,
        font_size: int = 22,
        focusable: bool = True,
        layer: int = 1000,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.width = max(1.0, float(width))
        self.height = max(1.0, float(height))
        self.enabled = True
        self.visible = True
        self.hovered = False
        self.focused = False
        self.focusable = bool(focusable)
        self.pressed = False
        self._armed = False
        self.on_click = on_click
        self.color = _color_or(color, (0.14, 0.20, 0.32, 1.0))
        self.hover_color = _color_or(hover_color, (0.20, 0.32, 0.52, 1.0))
        self.pressed_color = _color_or(pressed_color, (0.10, 0.16, 0.28, 1.0))
        self.focused_color = _color_or(focused_color, (0.24, 0.42, 0.68, 1.0))
        self.background = Rectangle2D(
            self.x,
            self.y,
            self.width,
            self.height,
            self.color,
            layer=layer,
            screen_space=True,
        )
        self.label = Text2D(
            text,
            self.x,
            self.y,
            _color_or(text_color, (1.0, 1.0, 1.0, 1.0)),
            font_size=font_size,
            layer=layer + 1,
            screen_space=True,
        )

    @property
    def children(self) -> tuple[object, ...]:
        return (self.background, self.label)

    @property
    def text(self) -> str:
        return self.label.text

    @text.setter
    def text(self, value: str) -> None:
        self.label.text = str(value)

    def contains(self, x: float, y: float) -> bool:
        half_w = self.width * 0.5
        half_h = self.height * 0.5
        return self.x - half_w <= x <= self.x + half_w and self.y - half_h <= y <= self.y + half_h

    def _sync(self) -> None:
        self.background.x = self.x
        self.background.y = self.y
        self.background.width = self.width
        self.background.height = self.height
        self.background.enabled = self.enabled
        self.background.visible = self.visible
        self.label.x = self.x
        self.label.y = self.y
        self.label.enabled = self.enabled
        self.label.visible = self.visible
        if self.pressed:
            self.background.color = self.pressed_color
        elif self.hovered:
            self.background.color = self.hover_color
        elif self.focused:
            self.background.color = self.focused_color
        else:
            self.background.color = self.color


class UIProgressBar:
    def __init__(
        self,
        x: float,
        y: float,
        width: float = 260.0,
        height: float = 24.0,
        *,
        value: float = 0.0,
        background_color: Color | None = None,
        fill_color: Color | None = None,
        layer: int = 1000,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.width = max(1.0, float(width))
        self.height = max(1.0, float(height))
        self.background = Rectangle2D(
            self.x,
            self.y,
            self.width,
            self.height,
            _color_or(background_color, (0.10, 0.12, 0.16, 1.0)),
            layer=layer,
            screen_space=True,
        )
        self.fill = Rectangle2D(
            self.x,
            self.y,
            1.0,
            self.height,
            _color_or(fill_color, (0.20, 0.75, 0.42, 1.0)),
            layer=layer + 1,
            screen_space=True,
        )
        self._value = 0.0
        self.value = value

    @property
    def children(self) -> tuple[object, ...]:
        return (self.background, self.fill)

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, float(value)))
        self._sync()

    def _sync(self) -> None:
        self.background.x = self.x
        self.background.y = self.y
        self.background.width = self.width
        self.background.height = self.height
        fill_width = self.width * self._value
        self.fill.width = max(0.001, fill_width)
        self.fill.height = self.height
        self.fill.x = self.x - self.width * 0.5 + fill_width * 0.5
        self.fill.y = self.y
        self.fill.visible = self._value > 0.0


UIControl = UILabel | UIPanel | UIButton | UIProgressBar


class UIManager:
    """Creator-facing UI registry with mouse, focus and responsive layout support."""

    def __init__(self, scene: Scene) -> None:
        from .ui_navigation import UIFocusManager

        self.scene = scene
        self._controls: list[UIControl] = []
        self._containers: list[UIContainer] = []
        self.focus: UIFocusManager = UIFocusManager()

    @property
    def controls(self) -> tuple[UIControl, ...]:
        return tuple(self._controls)

    @property
    def containers(self) -> tuple[UIContainer, ...]:
        return tuple(self._containers)

    def add(self, control: T) -> T:
        if not any(existing is control for existing in self._controls):
            self._controls.append(control)
            self.scene.add_many(*control.children)
            if isinstance(control, UIButton):
                self.focus.add(control)
        return control

    def remove(self, control: object) -> bool:
        for index, existing in enumerate(self._controls):
            if existing is control:
                del self._controls[index]
                for child in existing.children:
                    self.scene.remove(child)
                if isinstance(existing, UIButton):
                    self.focus.remove(existing)
                for container in self._containers:
                    container.remove(existing)
                return True
        return False

    def clear(self) -> None:
        for control in tuple(self._controls):
            self.remove(control)
        self._containers.clear()

    def label(self, text: str, x: float = 0.0, y: float = 0.0, **kwargs: object) -> UILabel:
        return self.add(UILabel(text, x, y, **kwargs))

    def panel(self, x: float, y: float, width: float, height: float, **kwargs: object) -> UIPanel:
        return self.add(UIPanel(x, y, width, height, **kwargs))

    def button(
        self,
        text: str,
        x: float,
        y: float,
        width: float = 220.0,
        height: float = 56.0,
        **kwargs: object,
    ) -> UIButton:
        return self.add(UIButton(text, x, y, width, height, **kwargs))

    def progress_bar(
        self,
        x: float,
        y: float,
        width: float = 260.0,
        height: float = 24.0,
        **kwargs: object,
    ) -> UIProgressBar:
        return self.add(UIProgressBar(x, y, width, height, **kwargs))

    def container(
        self,
        *controls: UIControl,
        x: float = 0.0,
        y: float = 0.0,
        direction: str = "vertical",
        spacing: float = 12.0,
        layout: UILayout | None = None,
    ) -> UIContainer:
        from .ui_layout import UIContainer

        for control in controls:
            self.add(control)
        container = UIContainer(
            *controls,
            x=x,
            y=y,
            direction=direction,
            spacing=spacing,
            layout=layout,
        )
        self._containers.append(container)
        return container

    def _update_pointer(self, input_manager: InputManager, width: int, height: int) -> None:
        pointer_x = input_manager.mouse_x - width * 0.5
        pointer_y = height * 0.5 - input_manager.mouse_y
        just_pressed = input_manager.mouse_button_pressed(0)
        just_released = input_manager.mouse_button_released(0)

        buttons = [control for control in self._controls if isinstance(control, UIButton)]
        active_hover: UIButton | None = None
        for button in reversed(buttons):
            if button.enabled and button.visible and button.contains(pointer_x, pointer_y):
                active_hover = button
                break

        if active_hover is not None:
            self.focus.focus(active_hover)

        for button in buttons:
            button.hovered = button is active_hover
            if just_pressed:
                button._armed = button.hovered and button.enabled
                button.pressed = button._armed
            elif input_manager.mouse_button(0):
                button.pressed = button._armed
            if just_released:
                clicked = button._armed and button.hovered and button.enabled
                button._armed = False
                button.pressed = False
                if clicked and button.on_click is not None:
                    button.on_click(button)

    def update(self, input_manager: InputManager, width: int, height: int) -> None:
        for container in self._containers:
            container.arrange(width, height)

        self._update_pointer(input_manager, width, height)
        focused = self.focus.update(input_manager)

        for control in self._controls:
            if isinstance(control, UIButton):
                control.focused = control is focused
                control._sync()
            else:
                sync = getattr(control, "_sync", None)
                if callable(sync):
                    sync()
