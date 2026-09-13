from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UIAnchor(str, Enum):
    CENTER = "center"
    TOP_LEFT = "top_left"
    TOP = "top"
    TOP_RIGHT = "top_right"
    LEFT = "left"
    RIGHT = "right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM = "bottom"
    BOTTOM_RIGHT = "bottom_right"


class UILayoutDirection(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass(slots=True)
class UILayout:
    """Viewport-relative placement and scaling policy for game UI."""

    anchor: UIAnchor = UIAnchor.CENTER
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_with_viewport: bool = False
    reference_width: float = 1280.0
    reference_height: float = 720.0
    min_scale: float = 0.5
    max_scale: float = 2.0

    def scale_for(self, width: int, height: int) -> float:
        if not self.scale_with_viewport:
            return 1.0
        scale = min(
            float(width) / max(1.0, float(self.reference_width)),
            float(height) / max(1.0, float(self.reference_height)),
        )
        return max(float(self.min_scale), min(float(self.max_scale), scale))

    def position_for(self, width: int, height: int) -> tuple[float, float, float]:
        scale = self.scale_for(width, height)
        half_w = float(width) * 0.5
        half_h = float(height) * 0.5
        x = 0.0
        y = 0.0
        if self.anchor in (UIAnchor.TOP_LEFT, UIAnchor.LEFT, UIAnchor.BOTTOM_LEFT):
            x = -half_w
        elif self.anchor in (UIAnchor.TOP_RIGHT, UIAnchor.RIGHT, UIAnchor.BOTTOM_RIGHT):
            x = half_w
        if self.anchor in (UIAnchor.TOP_LEFT, UIAnchor.TOP, UIAnchor.TOP_RIGHT):
            y = half_h
        elif self.anchor in (UIAnchor.BOTTOM_LEFT, UIAnchor.BOTTOM, UIAnchor.BOTTOM_RIGHT):
            y = -half_h
        return (x + self.offset_x * scale, y + self.offset_y * scale, scale)


def _scale_control_text(control: object, text_object: object, scale: float) -> None:
    if text_object is None or not hasattr(text_object, "scale"):
        return
    base_attr = "_layout_base_text_scale"
    if not hasattr(control, base_attr):
        setattr(control, base_attr, float(getattr(text_object, "scale")))
    setattr(text_object, "scale", float(getattr(control, base_attr)) * float(scale))


def place_control(control: object, x: float, y: float, scale: float = 1.0) -> None:
    """Place a supported control while preserving its creator-authored base size."""

    if hasattr(control, "x"):
        control.x = float(x)
    if hasattr(control, "y"):
        control.y = float(y)
    for attr in ("width", "height"):
        if not hasattr(control, attr):
            continue
        base_attr = f"_layout_base_{attr}"
        if not hasattr(control, base_attr):
            setattr(control, base_attr, float(getattr(control, attr)))
        setattr(control, attr, max(1.0, float(getattr(control, base_attr)) * float(scale)))

    text_object = getattr(control, "text_object", None)
    if text_object is None:
        text_object = getattr(control, "label", None)
    _scale_control_text(control, text_object, scale)

    sync = getattr(control, "_sync", None)
    if callable(sync):
        sync()


class UIContainer:
    """Simple deterministic row/column layout container.

    Existing controls remain regular SwirEngine controls; the container only owns placement. This
    keeps the 1.x API compatible while eliminating per-resolution coordinate rewrites.
    """

    def __init__(
        self,
        *controls: object,
        x: float = 0.0,
        y: float = 0.0,
        direction: UILayoutDirection | str = UILayoutDirection.VERTICAL,
        spacing: float = 12.0,
        layout: UILayout | None = None,
    ) -> None:
        self.controls = list(controls)
        self.x = float(x)
        self.y = float(y)
        self.direction = UILayoutDirection(direction)
        self.spacing = float(spacing)
        self.layout = layout

    @property
    def children(self) -> tuple[object, ...]:
        return tuple(child for control in self.controls for child in getattr(control, "children", ()))

    def add(self, control: object) -> object:
        if not any(existing is control for existing in self.controls):
            self.controls.append(control)
        return control

    def remove(self, control: object) -> bool:
        for index, existing in enumerate(self.controls):
            if existing is control:
                del self.controls[index]
                return True
        return False

    def arrange(self, width: int, height: int) -> None:
        origin_x = self.x
        origin_y = self.y
        scale = 1.0
        if self.layout is not None:
            origin_x, origin_y, scale = self.layout.position_for(width, height)
            origin_x += self.x * scale
            origin_y += self.y * scale
        sizes = [
            (
                float(getattr(control, "_layout_base_width", getattr(control, "width", 0.0))) * scale,
                float(getattr(control, "_layout_base_height", getattr(control, "height", 0.0))) * scale,
            )
            for control in self.controls
        ]
        gap = self.spacing * scale
        if self.direction is UILayoutDirection.VERTICAL:
            total = sum(item_height for _, item_height in sizes) + gap * max(0, len(sizes) - 1)
            cursor = origin_y + total * 0.5
            for control, (_, control_height) in zip(self.controls, sizes):
                cursor -= control_height * 0.5
                place_control(control, origin_x, cursor, scale)
                cursor -= control_height * 0.5 + gap
        else:
            total = sum(item_width for item_width, _ in sizes) + gap * max(0, len(sizes) - 1)
            cursor = origin_x - total * 0.5
            for control, (control_width, _) in zip(self.controls, sizes):
                cursor += control_width * 0.5
                place_control(control, cursor, origin_y, scale)
                cursor += control_width * 0.5 + gap
