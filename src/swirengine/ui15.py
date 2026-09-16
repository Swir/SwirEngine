from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .core.scene import Scene
from .math.types import Color
from .ui import UIButton, UILabel, UIManager, UIPanel, UIProgressBar


class UIAxis(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class UIAlign(str, Enum):
    START = "start"
    CENTER = "center"
    END = "end"
    STRETCH = "stretch"


class UIJustify(str, Enum):
    START = "start"
    CENTER = "center"
    END = "end"
    SPACE_BETWEEN = "space_between"


class UINavigationDirection(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class UIWidgetKind(str, Enum):
    STACK = "stack"
    PANEL = "panel"
    LABEL = "label"
    BUTTON = "button"
    PROGRESS = "progress"


def _finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


def _nonnegative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0.0:
        raise ValueError(f"{name} must be >= 0")
    return result


@dataclass(frozen=True, slots=True)
class UIInsets:
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    def __post_init__(self) -> None:
        for name in ("left", "top", "right", "bottom"):
            object.__setattr__(self, name, _nonnegative(getattr(self, name), name))

    @classmethod
    def all(cls, value: float) -> UIInsets:
        value = _nonnegative(value, "value")
        return cls(value, value, value, value)


@dataclass(frozen=True, slots=True)
class UIRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x - self.width * 0.5

    @property
    def right(self) -> float:
        return self.x + self.width * 0.5

    @property
    def top(self) -> float:
        return self.y + self.height * 0.5

    @property
    def bottom(self) -> float:
        return self.y - self.height * 0.5

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.bottom <= y <= self.top


@dataclass(frozen=True, slots=True)
class UITheme:
    panel: Color = Color(0.07, 0.09, 0.14, 0.96)
    text: Color = Color(0.96, 0.97, 1.0, 1.0)
    button: Color = Color(0.12, 0.19, 0.31, 1.0)
    button_hover: Color = Color(0.18, 0.31, 0.50, 1.0)
    button_pressed: Color = Color(0.08, 0.14, 0.25, 1.0)
    button_focused: Color = Color(0.22, 0.44, 0.75, 1.0)
    progress_background: Color = Color(0.09, 0.11, 0.16, 1.0)
    progress_fill: Color = Color(0.22, 0.74, 0.48, 1.0)

    @classmethod
    def high_contrast(cls) -> UITheme:
        return cls(
            panel=Color(0.02, 0.02, 0.03, 1.0),
            text=Color(1.0, 1.0, 1.0, 1.0),
            button=Color(0.08, 0.08, 0.10, 1.0),
            button_hover=Color(0.12, 0.35, 0.62, 1.0),
            button_pressed=Color(0.04, 0.18, 0.36, 1.0),
            button_focused=Color(0.10, 0.55, 1.0, 1.0),
            progress_background=Color(0.12, 0.12, 0.12, 1.0),
            progress_fill=Color(0.10, 0.85, 0.55, 1.0),
        )


@dataclass(frozen=True, slots=True)
class UIToolkitDiagnostics:
    nodes: int
    visible_nodes: int
    focusable_nodes: int
    layout_generation: int
    activations: int
    pointer_hits: int
    focused_id: str | None
    scale: float
    viewport: tuple[int, int] | None


class UIWidget:
    """A retained creator-facing UI node backed by the stable SwirEngine 1.x controls."""

    def __init__(
        self,
        widget_id: str,
        kind: UIWidgetKind | str,
        *,
        width: float,
        height: float,
        text: str = "",
        value: float = 0.0,
        axis: UIAxis | str = UIAxis.VERTICAL,
        gap: float = 12.0,
        padding: UIInsets | float = 0.0,
        align: UIAlign | str = UIAlign.CENTER,
        justify: UIJustify | str = UIJustify.CENTER,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        visible: bool = True,
        enabled: bool = True,
        focusable: bool | None = None,
        on_activate: Callable[[UIWidget], None] | None = None,
    ) -> None:
        normalized_id = str(widget_id).strip()
        if not normalized_id:
            raise ValueError("widget_id must not be empty")
        self.id = normalized_id
        self.kind = UIWidgetKind(kind)
        self.width = _positive(width, "width")
        self.height = _positive(height, "height")
        self.text = str(text)
        self.value = max(0.0, min(1.0, _finite(value, "value")))
        self.axis = UIAxis(axis)
        self.gap = _nonnegative(gap, "gap")
        self.padding = UIInsets.all(padding) if isinstance(padding, (int, float)) else padding
        self.align = UIAlign(align)
        self.justify = UIJustify(justify)
        self.offset_x = _finite(offset_x, "offset_x")
        self.offset_y = _finite(offset_y, "offset_y")
        self.visible = bool(visible)
        self.enabled = bool(enabled)
        self.focusable = self.kind is UIWidgetKind.BUTTON if focusable is None else bool(focusable)
        self.on_activate = on_activate
        self.parent: UIWidget | None = None
        self.children: list[UIWidget] = []
        self.control: UILabel | UIPanel | UIButton | UIProgressBar | None = None
        self.rect = UIRect(0.0, 0.0, self.width, self.height)
        self.effective_visible = bool(visible)
        self.effective_enabled = bool(enabled)

    def walk(self) -> Iterator[UIWidget]:
        yield self
        for child in self.children:
            yield from child.walk()

    def is_ancestor_of(self, other: UIWidget) -> bool:
        current = other.parent
        while current is not None:
            if current is self:
                return True
            current = current.parent
        return False


class UIToolkit:
    """SwirEngine 1.5 retained UI runtime.

    The toolkit is additive: rendering is delegated to the stable 1.x UI controls while this class
    owns retained hierarchy, responsive layout, theme propagation and deterministic focus/input.
    """

    ROOT_ID = "__root__"

    def __init__(
        self,
        scene: Scene,
        *,
        reference_width: float = 1280.0,
        reference_height: float = 720.0,
        min_scale: float = 0.5,
        max_scale: float = 2.0,
        theme: UITheme | None = None,
    ) -> None:
        self.scene = scene
        self.manager = UIManager(scene)
        self.reference_width = _positive(reference_width, "reference_width")
        self.reference_height = _positive(reference_height, "reference_height")
        self.min_scale = _positive(min_scale, "min_scale")
        self.max_scale = _positive(max_scale, "max_scale")
        if self.min_scale > self.max_scale:
            raise ValueError("min_scale must be <= max_scale")
        self.theme = theme or UITheme()
        self.root = UIWidget(
            self.ROOT_ID,
            UIWidgetKind.STACK,
            width=self.reference_width,
            height=self.reference_height,
            gap=0.0,
        )
        self._nodes: dict[str, UIWidget] = {self.ROOT_ID: self.root}
        self._focused_id: str | None = None
        self._armed_id: str | None = None
        self._hovered_id: str | None = None
        self._layout_generation = 0
        self._activations = 0
        self._pointer_hits = 0
        self._scale = 1.0
        self._viewport: tuple[int, int] | None = None

    @property
    def focused(self) -> UIWidget | None:
        return self._nodes.get(self._focused_id) if self._focused_id is not None else None

    @property
    def nodes(self) -> tuple[UIWidget, ...]:
        return tuple(self.root.walk())

    def find(self, widget_id: str) -> UIWidget | None:
        return self._nodes.get(str(widget_id))

    def _resolve(self, widget: UIWidget | str) -> UIWidget:
        if isinstance(widget, UIWidget):
            current = self._nodes.get(widget.id)
            if current is not widget:
                raise ValueError("widget does not belong to this toolkit")
            return widget
        resolved = self.find(widget)
        if resolved is None:
            raise KeyError(str(widget))
        return resolved

    def _new_control(self, widget: UIWidget) -> UILabel | UIPanel | UIButton | UIProgressBar | None:
        if widget.kind is UIWidgetKind.LABEL:
            return self.manager.label(widget.text, 0.0, 0.0, color=self.theme.text)
        if widget.kind is UIWidgetKind.PANEL:
            return self.manager.panel(0.0, 0.0, widget.width, widget.height, color=self.theme.panel)
        if widget.kind is UIWidgetKind.BUTTON:
            control = self.manager.button(
                widget.text,
                0.0,
                0.0,
                widget.width,
                widget.height,
                color=self.theme.button,
                hover_color=self.theme.button_hover,
                pressed_color=self.theme.button_pressed,
                focused_color=self.theme.button_focused,
                text_color=self.theme.text,
                focusable=False,
            )
            return control
        if widget.kind is UIWidgetKind.PROGRESS:
            return self.manager.progress_bar(
                0.0,
                0.0,
                widget.width,
                widget.height,
                value=widget.value,
                background_color=self.theme.progress_background,
                fill_color=self.theme.progress_fill,
            )
        return None

    def add(self, widget: UIWidget, *, parent: UIWidget | str = ROOT_ID) -> UIWidget:
        if widget.id in self._nodes:
            raise ValueError(f"duplicate widget id: {widget.id}")
        parent_widget = self._resolve(parent)
        if widget is parent_widget or widget.is_ancestor_of(parent_widget):
            raise ValueError("UI hierarchy cannot contain cycles")
        if widget.parent is not None:
            raise ValueError("widget already has a parent")
        if any(child.id in self._nodes for child in widget.walk()):
            raise ValueError("widget subtree contains an id already registered in this toolkit")
        subtree = tuple(widget.walk())
        if len({child.id for child in subtree}) != len(subtree):
            raise ValueError("widget subtree contains duplicate ids")
        parent_widget.children.append(widget)
        widget.parent = parent_widget
        for child in subtree:
            self._nodes[child.id] = child
            if child is not widget and child.parent is None:
                raise ValueError("detached descendants are not supported")
            child.control = self._new_control(child)
        return widget

    def _make(
        self,
        widget_id: str,
        kind: UIWidgetKind,
        *,
        parent: UIWidget | str = ROOT_ID,
        **kwargs: Any,
    ) -> UIWidget:
        return self.add(UIWidget(widget_id, kind, **kwargs), parent=parent)

    def stack(
        self,
        widget_id: str,
        width: float,
        height: float,
        *,
        parent: UIWidget | str = ROOT_ID,
        axis: UIAxis | str = UIAxis.VERTICAL,
        gap: float = 12.0,
        padding: UIInsets | float = 0.0,
        align: UIAlign | str = UIAlign.CENTER,
        justify: UIJustify | str = UIJustify.CENTER,
        **kwargs: Any,
    ) -> UIWidget:
        return self._make(
            widget_id,
            UIWidgetKind.STACK,
            parent=parent,
            width=width,
            height=height,
            axis=axis,
            gap=gap,
            padding=padding,
            align=align,
            justify=justify,
            **kwargs,
        )

    def panel(
        self,
        widget_id: str,
        width: float,
        height: float,
        *,
        parent: UIWidget | str = ROOT_ID,
        axis: UIAxis | str = UIAxis.VERTICAL,
        gap: float = 12.0,
        padding: UIInsets | float = 20.0,
        align: UIAlign | str = UIAlign.CENTER,
        justify: UIJustify | str = UIJustify.CENTER,
        **kwargs: Any,
    ) -> UIWidget:
        return self._make(
            widget_id,
            UIWidgetKind.PANEL,
            parent=parent,
            width=width,
            height=height,
            axis=axis,
            gap=gap,
            padding=padding,
            align=align,
            justify=justify,
            **kwargs,
        )

    def label(
        self,
        widget_id: str,
        text: str,
        *,
        parent: UIWidget | str = ROOT_ID,
        width: float = 260.0,
        height: float = 36.0,
        **kwargs: Any,
    ) -> UIWidget:
        return self._make(
            widget_id,
            UIWidgetKind.LABEL,
            parent=parent,
            width=width,
            height=height,
            text=text,
            focusable=False,
            **kwargs,
        )

    def button(
        self,
        widget_id: str,
        text: str,
        *,
        parent: UIWidget | str = ROOT_ID,
        width: float = 240.0,
        height: float = 56.0,
        on_activate: Callable[[UIWidget], None] | None = None,
        **kwargs: Any,
    ) -> UIWidget:
        return self._make(
            widget_id,
            UIWidgetKind.BUTTON,
            parent=parent,
            width=width,
            height=height,
            text=text,
            on_activate=on_activate,
            **kwargs,
        )

    def progress(
        self,
        widget_id: str,
        *,
        parent: UIWidget | str = ROOT_ID,
        width: float = 280.0,
        height: float = 24.0,
        value: float = 0.0,
        **kwargs: Any,
    ) -> UIWidget:
        return self._make(
            widget_id,
            UIWidgetKind.PROGRESS,
            parent=parent,
            width=width,
            height=height,
            value=value,
            focusable=False,
            **kwargs,
        )

    def reparent(self, widget: UIWidget | str, parent: UIWidget | str) -> UIWidget:
        node = self._resolve(widget)
        parent_node = self._resolve(parent)
        if node is self.root:
            raise ValueError("root cannot be reparented")
        if node is parent_node or node.is_ancestor_of(parent_node):
            raise ValueError("UI hierarchy cannot contain cycles")
        assert node.parent is not None
        node.parent.children.remove(node)
        parent_node.children.append(node)
        node.parent = parent_node
        return node

    def remove(self, widget: UIWidget | str) -> bool:
        node = self._resolve(widget)
        if node is self.root:
            raise ValueError("root cannot be removed")
        subtree = tuple(node.walk())
        assert node.parent is not None
        node.parent.children.remove(node)
        for child in reversed(subtree):
            if child.control is not None:
                self.manager.remove(child.control)
            self._nodes.pop(child.id, None)
        removed_ids = {child.id for child in subtree}
        if self._focused_id in removed_ids:
            self._focused_id = None
        if self._armed_id in removed_ids:
            self._armed_id = None
        if self._hovered_id in removed_ids:
            self._hovered_id = None
        node.parent = None
        return True

    def set_theme(self, theme: UITheme) -> None:
        if not isinstance(theme, UITheme):
            raise TypeError("theme must be a UITheme")
        self.theme = theme
        self._sync_all_controls()

    def _scale_for(self, width: int, height: int) -> float:
        if width <= 0 or height <= 0:
            raise ValueError("viewport dimensions must be positive")
        scale = min(width / self.reference_width, height / self.reference_height)
        return max(self.min_scale, min(self.max_scale, scale))

    @staticmethod
    def _cross_position(parent: UIRect, size: float, axis: UIAxis, align: UIAlign, padding: UIInsets) -> float:
        if axis is UIAxis.VERTICAL:
            low = parent.left + padding.left
            high = parent.right - padding.right
        else:
            low = parent.bottom + padding.bottom
            high = parent.top - padding.top
        if align is UIAlign.START:
            return low + size * 0.5
        if align is UIAlign.END:
            return high - size * 0.5
        return (low + high) * 0.5

    def _layout_children(self, parent: UIWidget, scale: float, inherited_visible: bool, inherited_enabled: bool) -> None:
        parent.effective_visible = inherited_visible and parent.visible
        parent.effective_enabled = inherited_enabled and parent.enabled
        if parent.control is not None:
            self._sync_control(parent, scale)

        active = [child for child in parent.children if child.visible and parent.effective_visible]
        for child in parent.children:
            if child not in active:
                child.effective_visible = False
                child.effective_enabled = False
                self._hide_subtree(child)
        if not active:
            return

        padding = UIInsets(
            parent.padding.left * scale,
            parent.padding.top * scale,
            parent.padding.right * scale,
            parent.padding.bottom * scale,
        )
        gap = parent.gap * scale
        if parent.axis is UIAxis.VERTICAL:
            inner_main = max(0.0, parent.rect.height - padding.top - padding.bottom)
            sizes = [child.height * scale for child in active]
            default_gap_total = gap * max(0, len(active) - 1)
            content = sum(sizes) + default_gap_total
            actual_gap = gap
            if parent.justify is UIJustify.SPACE_BETWEEN and len(active) > 1:
                actual_gap = max(0.0, (inner_main - sum(sizes)) / (len(active) - 1))
                content = sum(sizes) + actual_gap * (len(active) - 1)
            top = parent.rect.top - padding.top
            if parent.justify is UIJustify.START or parent.justify is UIJustify.SPACE_BETWEEN:
                cursor = top
            elif parent.justify is UIJustify.END:
                cursor = parent.rect.bottom + padding.bottom + content
            else:
                cursor = parent.rect.y + content * 0.5
            for child, main_size in zip(active, sizes):
                width = child.width * scale
                available_cross = max(1.0, parent.rect.width - padding.left - padding.right)
                if parent.align is UIAlign.STRETCH:
                    width = available_cross
                x = self._cross_position(parent.rect, width, parent.axis, parent.align, padding)
                y = cursor - main_size * 0.5
                child.rect = UIRect(
                    x + child.offset_x * scale,
                    y + child.offset_y * scale,
                    width,
                    main_size,
                )
                cursor -= main_size + actual_gap
                self._layout_children(child, scale, parent.effective_visible, parent.effective_enabled)
        else:
            inner_main = max(0.0, parent.rect.width - padding.left - padding.right)
            sizes = [child.width * scale for child in active]
            default_gap_total = gap * max(0, len(active) - 1)
            content = sum(sizes) + default_gap_total
            actual_gap = gap
            if parent.justify is UIJustify.SPACE_BETWEEN and len(active) > 1:
                actual_gap = max(0.0, (inner_main - sum(sizes)) / (len(active) - 1))
                content = sum(sizes) + actual_gap * (len(active) - 1)
            left = parent.rect.left + padding.left
            if parent.justify is UIJustify.START or parent.justify is UIJustify.SPACE_BETWEEN:
                cursor = left
            elif parent.justify is UIJustify.END:
                cursor = parent.rect.right - padding.right - content
            else:
                cursor = parent.rect.x - content * 0.5
            for child, main_size in zip(active, sizes):
                height = child.height * scale
                available_cross = max(1.0, parent.rect.height - padding.top - padding.bottom)
                if parent.align is UIAlign.STRETCH:
                    height = available_cross
                y = self._cross_position(parent.rect, height, parent.axis, parent.align, padding)
                x = cursor + main_size * 0.5
                child.rect = UIRect(
                    x + child.offset_x * scale,
                    y + child.offset_y * scale,
                    main_size,
                    height,
                )
                cursor += main_size + actual_gap
                self._layout_children(child, scale, parent.effective_visible, parent.effective_enabled)

    def _hide_subtree(self, node: UIWidget) -> None:
        node.effective_visible = False
        node.effective_enabled = False
        if node.control is not None:
            if hasattr(node.control, "visible"):
                node.control.visible = False
            for child in node.control.children:
                child.visible = False
        for child in node.children:
            self._hide_subtree(child)

    def layout(self, width: int, height: int) -> float:
        width = int(width)
        height = int(height)
        scale = self._scale_for(width, height)
        self._scale = scale
        self._viewport = (width, height)
        self.root.rect = UIRect(0.0, 0.0, self.reference_width * scale, self.reference_height * scale)
        self._layout_children(self.root, scale, True, True)
        self._layout_generation += 1
        if self._focused_id is not None and self.focused not in self.focusable_widgets():
            self._focused_id = None
        self._sync_interaction_styles()
        return scale

    def _sync_control(self, widget: UIWidget, scale: float) -> None:
        control = widget.control
        if control is None:
            return
        rect = widget.rect
        if hasattr(control, "x"):
            control.x = rect.x
        if hasattr(control, "y"):
            control.y = rect.y
        if hasattr(control, "width"):
            control.width = max(1.0, rect.width)
        if hasattr(control, "height"):
            control.height = max(1.0, rect.height)
        if isinstance(control, UILabel):
            control.text = widget.text
            control.text_object.color = self.theme.text
            control.text_object.scale = scale
            control.text_object.visible = widget.effective_visible
            control.text_object.enabled = widget.effective_enabled
        elif isinstance(control, UIPanel):
            control.background.color = self.theme.panel
            control.background.visible = widget.effective_visible
            control.background.enabled = widget.effective_enabled
            control._sync()
        elif isinstance(control, UIButton):
            control.text = widget.text
            control.color = self.theme.button
            control.hover_color = self.theme.button_hover
            control.pressed_color = self.theme.button_pressed
            control.focused_color = self.theme.button_focused
            control.label.color = self.theme.text
            control.label.scale = scale
            control.visible = widget.effective_visible
            control.enabled = widget.effective_enabled
            control._sync()
        elif isinstance(control, UIProgressBar):
            control.value = widget.value
            control.background.color = self.theme.progress_background
            control.fill.color = self.theme.progress_fill
            control.background.visible = widget.effective_visible
            control.background.enabled = widget.effective_enabled
            control.fill.enabled = widget.effective_enabled
            control._sync()
            control.fill.visible = widget.effective_visible and widget.value > 0.0

    def _sync_all_controls(self) -> None:
        for widget in self.root.walk():
            if widget.control is not None:
                self._sync_control(widget, self._scale)
        self._sync_interaction_styles()

    def focusable_widgets(self) -> tuple[UIWidget, ...]:
        return tuple(
            widget
            for widget in self.root.walk()
            if widget is not self.root
            and widget.focusable
            and widget.effective_visible
            and widget.effective_enabled
        )

    def focus(self, widget: UIWidget | str | None) -> UIWidget | None:
        if widget is None:
            self._focused_id = None
            self._sync_interaction_styles()
            return None
        node = self._resolve(widget)
        if node not in self.focusable_widgets():
            return self.focused
        self._focused_id = node.id
        self._sync_interaction_styles()
        return node

    def focus_next(self, step: int = 1) -> UIWidget | None:
        candidates = self.focusable_widgets()
        if not candidates:
            self._focused_id = None
            self._sync_interaction_styles()
            return None
        focused = self.focused
        if focused not in candidates:
            target = candidates[0] if step >= 0 else candidates[-1]
        else:
            index = candidates.index(focused)
            target = candidates[(index + step) % len(candidates)]
        return self.focus(target)

    def focus_move(self, direction: UINavigationDirection | str) -> UIWidget | None:
        direction = UINavigationDirection(direction)
        candidates = self.focusable_widgets()
        current = self.focused
        if not candidates:
            return self.focus(None)
        if current not in candidates:
            return self.focus(candidates[0])
        best: tuple[float, UIWidget] | None = None
        for candidate in candidates:
            if candidate is current:
                continue
            dx = candidate.rect.x - current.rect.x
            dy = candidate.rect.y - current.rect.y
            if direction is UINavigationDirection.LEFT and dx >= 0.0:
                continue
            if direction is UINavigationDirection.RIGHT and dx <= 0.0:
                continue
            if direction is UINavigationDirection.UP and dy <= 0.0:
                continue
            if direction is UINavigationDirection.DOWN and dy >= 0.0:
                continue
            if direction in (UINavigationDirection.LEFT, UINavigationDirection.RIGHT):
                primary, secondary = abs(dx), abs(dy)
            else:
                primary, secondary = abs(dy), abs(dx)
            score = primary * 1024.0 + secondary
            if best is None or score < best[0]:
                best = (score, candidate)
        if best is None:
            return current
        return self.focus(best[1])

    def hit_test(self, x: float, y: float) -> UIWidget | None:
        x = _finite(x, "x")
        y = _finite(y, "y")
        for widget in reversed(self.focusable_widgets()):
            if widget.rect.contains(x, y):
                self._pointer_hits += 1
                return widget
        return None

    def _activate(self, widget: UIWidget) -> bool:
        if widget not in self.focusable_widgets():
            return False
        self._activations += 1
        if widget.on_activate is not None:
            widget.on_activate(widget)
        return True

    def activate_focused(self) -> bool:
        focused = self.focused
        return False if focused is None else self._activate(focused)

    def pointer(self, x: float, y: float, *, pressed: bool, released: bool, down: bool) -> UIWidget | None:
        hovered = self.hit_test(x, y)
        self._hovered_id = hovered.id if hovered is not None else None
        if pressed:
            self._armed_id = self._hovered_id
            if hovered is not None:
                self.focus(hovered)
        if released:
            armed = self._nodes.get(self._armed_id) if self._armed_id is not None else None
            if armed is not None and armed is hovered:
                self._activate(armed)
            self._armed_id = None
        elif not down and not pressed:
            self._armed_id = None
        self._sync_interaction_styles()
        return hovered

    def _sync_interaction_styles(self) -> None:
        for widget in self.root.walk():
            control = widget.control
            if not isinstance(control, UIButton):
                continue
            control.hovered = widget.id == self._hovered_id
            control.focused = widget.id == self._focused_id
            control.pressed = widget.id == self._armed_id
            control._sync()

    @staticmethod
    def _call_bool(target: Any, name: str, *args: Any) -> bool:
        method = getattr(target, name, None)
        if not callable(method):
            return False
        try:
            return bool(method(*args))
        except (KeyError, TypeError, ValueError):
            return False

    @classmethod
    def _gamepad_pressed(cls, input_manager: Any, button: str) -> bool:
        gamepads_method = getattr(input_manager, "gamepads", None)
        ids = tuple(gamepads_method()) if callable(gamepads_method) else (0,)
        if not ids:
            ids = (0,)
        return any(cls._call_bool(input_manager, "gamepad_button_pressed", button, int(gamepad_id)) for gamepad_id in ids)

    def update(self, input_manager: Any, width: int, height: int) -> None:
        self.layout(width, height)
        mouse_x = _finite(getattr(input_manager, "mouse_x", width * 0.5), "mouse_x") - width * 0.5
        mouse_y = height * 0.5 - _finite(getattr(input_manager, "mouse_y", height * 0.5), "mouse_y")
        self.pointer(
            mouse_x,
            mouse_y,
            pressed=self._call_bool(input_manager, "mouse_button_pressed", 0),
            released=self._call_bool(input_manager, "mouse_button_released", 0),
            down=self._call_bool(input_manager, "mouse_button", 0),
        )

        if self._call_bool(input_manager, "key_pressed", "tab"):
            shift = self._call_bool(input_manager, "key", "shift")
            self.focus_next(-1 if shift else 1)
        elif self._call_bool(input_manager, "key_pressed", "left") or self._gamepad_pressed(input_manager, "dpad_left"):
            self.focus_move(UINavigationDirection.LEFT)
        elif self._call_bool(input_manager, "key_pressed", "right") or self._gamepad_pressed(input_manager, "dpad_right"):
            self.focus_move(UINavigationDirection.RIGHT)
        elif self._call_bool(input_manager, "key_pressed", "up") or self._gamepad_pressed(input_manager, "dpad_up"):
            self.focus_move(UINavigationDirection.UP)
        elif self._call_bool(input_manager, "key_pressed", "down") or self._gamepad_pressed(input_manager, "dpad_down"):
            self.focus_move(UINavigationDirection.DOWN)

        if (
            self._call_bool(input_manager, "key_pressed", "enter")
            or self._call_bool(input_manager, "key_pressed", "space")
            or self._gamepad_pressed(input_manager, "a")
        ):
            self.activate_focused()

    def diagnostics(self) -> UIToolkitDiagnostics:
        nodes = tuple(self.root.walk())
        return UIToolkitDiagnostics(
            nodes=max(0, len(nodes) - 1),
            visible_nodes=sum(1 for node in nodes if node is not self.root and node.effective_visible),
            focusable_nodes=len(self.focusable_widgets()),
            layout_generation=self._layout_generation,
            activations=self._activations,
            pointer_hits=self._pointer_hits,
            focused_id=self._focused_id,
            scale=self._scale,
            viewport=self._viewport,
        )

    @staticmethod
    def _color_tuple(color: Color) -> tuple[float, float, float, float]:
        return (color.r, color.g, color.b, color.a)

    def snapshot(self) -> dict[str, Any]:
        theme = {
            name: self._color_tuple(getattr(self.theme, name))
            for name in (
                "panel",
                "text",
                "button",
                "button_hover",
                "button_pressed",
                "button_focused",
                "progress_background",
                "progress_fill",
            )
        }
        nodes = []
        for widget in self.root.walk():
            if widget is self.root:
                continue
            nodes.append(
                {
                    "id": widget.id,
                    "kind": widget.kind.value,
                    "parent": widget.parent.id if widget.parent is not None else None,
                    "width": widget.width,
                    "height": widget.height,
                    "text": widget.text,
                    "value": widget.value,
                    "axis": widget.axis.value,
                    "gap": widget.gap,
                    "padding": (
                        widget.padding.left,
                        widget.padding.top,
                        widget.padding.right,
                        widget.padding.bottom,
                    ),
                    "align": widget.align.value,
                    "justify": widget.justify.value,
                    "offset": (widget.offset_x, widget.offset_y),
                    "visible": widget.visible,
                    "enabled": widget.enabled,
                    "focusable": widget.focusable,
                }
            )
        return {
            "reference": (self.reference_width, self.reference_height),
            "scale_limits": (self.min_scale, self.max_scale),
            "theme": theme,
            "nodes": nodes,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "UIAlign",
    "UIAxis",
    "UIInsets",
    "UIJustify",
    "UINavigationDirection",
    "UIRect",
    "UITheme",
    "UIToolkit",
    "UIToolkitDiagnostics",
    "UIWidget",
    "UIWidgetKind",
]
