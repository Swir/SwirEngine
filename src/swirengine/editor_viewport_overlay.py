from __future__ import annotations

import math
from dataclasses import dataclass

from .graphics.camera import Camera2D
from .graphics.camera3d import Camera3D
from .math.types import Vec2, Vec3


@dataclass(frozen=True, slots=True)
class ViewportOverlayLine:
    """One screen-space editor overlay line in framebuffer coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    role: str


@dataclass(frozen=True, slots=True)
class ViewportOverlayFrame:
    """Deterministic grid/gizmo overlay ready for a desktop or web editor front-end."""

    width: int
    height: int
    lines: tuple[ViewportOverlayLine, ...]


class EditorViewportOverlay:
    """Build lightweight production-editor overlays without coupling them to Tk or OpenGL."""

    def build(
        self,
        *,
        mode: str,
        camera_2d: Camera2D,
        camera_3d: Camera3D,
        width: int,
        height: int,
        grid_visible: bool,
        grid_spacing: float,
        selected_target: object | None,
        gizmo: str,
    ) -> ViewportOverlayFrame:
        width = self._positive_int(width, "viewport width")
        height = self._positive_int(height, "viewport height")
        spacing = self._positive_number(grid_spacing, "grid spacing")
        if mode not in {"2d", "3d"}:
            raise ValueError(f"unsupported viewport mode {mode!r}")

        lines: list[ViewportOverlayLine] = []
        if grid_visible:
            if mode == "2d":
                lines.extend(self.grid_2d(camera_2d, width, height, spacing))
            else:
                lines.extend(self.grid_3d(camera_3d, width, height, spacing))
        if selected_target is not None and gizmo != "none":
            if mode == "2d":
                lines.extend(self.gizmo_2d(camera_2d, selected_target, width, height, gizmo))
            else:
                lines.extend(
                    self.gizmo_3d(
                        camera_3d, selected_target, width, height, spacing, gizmo
                    )
                )
        return ViewportOverlayFrame(width, height, tuple(lines))

    def grid_2d(
        self,
        camera: Camera2D,
        width: int,
        height: int,
        base_spacing: float,
        *,
        min_pixels: float = 28.0,
        max_lines: int = 192,
    ) -> tuple[ViewportOverlayLine, ...]:
        width = self._positive_int(width, "viewport width")
        height = self._positive_int(height, "viewport height")
        spacing = self._adaptive_spacing(camera.safe_zoom, base_spacing, min_pixels)
        half_w = width * 0.5 / camera.safe_zoom
        half_h = height * 0.5 / camera.safe_zoom
        left = camera.x - half_w
        right = camera.x + half_w
        bottom = camera.y - half_h
        top = camera.y + half_h

        lines: list[ViewportOverlayLine] = []
        first_x = math.floor(left / spacing) * spacing
        x = first_x
        while x <= right + 1e-9 and len(lines) < max_lines:
            screen = self.world_to_screen_2d(camera, Vec2(x, 0.0), width, height)
            index = int(round(x / spacing))
            role = "axis_y" if abs(x) <= 1e-9 else "grid_major" if index % 5 == 0 else "grid_minor"
            lines.append(ViewportOverlayLine(screen.x, 0.0, screen.x, float(height), role))
            x += spacing

        first_y = math.floor(bottom / spacing) * spacing
        y = first_y
        while y <= top + 1e-9 and len(lines) < max_lines:
            screen = self.world_to_screen_2d(camera, Vec2(0.0, y), width, height)
            index = int(round(y / spacing))
            role = "axis_x" if abs(y) <= 1e-9 else "grid_major" if index % 5 == 0 else "grid_minor"
            lines.append(ViewportOverlayLine(0.0, screen.y, float(width), screen.y, role))
            y += spacing
        return tuple(lines)

    def grid_3d(
        self,
        camera: Camera3D,
        width: int,
        height: int,
        base_spacing: float,
        *,
        half_cells: int = 10,
    ) -> tuple[ViewportOverlayLine, ...]:
        width = self._positive_int(width, "viewport width")
        height = self._positive_int(height, "viewport height")
        spacing = self._positive_number(base_spacing, "grid spacing")
        if half_cells < 1:
            raise ValueError("half_cells must be at least 1")

        target = camera.target
        center_x = round(target.x / spacing) * spacing
        center_z = round(target.z / spacing) * spacing
        extent = spacing * half_cells
        lines: list[ViewportOverlayLine] = []
        for offset_index in range(-half_cells, half_cells + 1):
            offset = offset_index * spacing
            x = center_x + offset
            first = self.project_3d(camera, Vec3(x, 0.0, center_z - extent), width, height)
            second = self.project_3d(camera, Vec3(x, 0.0, center_z + extent), width, height)
            if first is not None and second is not None:
                role = (
                    "axis_z"
                    if abs(x) <= 1e-9
                    else "grid_major" if offset_index % 5 == 0 else "grid_minor"
                )
                lines.append(ViewportOverlayLine(first.x, first.y, second.x, second.y, role))

            z = center_z + offset
            first = self.project_3d(camera, Vec3(center_x - extent, 0.0, z), width, height)
            second = self.project_3d(camera, Vec3(center_x + extent, 0.0, z), width, height)
            if first is not None and second is not None:
                role = (
                    "axis_x"
                    if abs(z) <= 1e-9
                    else "grid_major" if offset_index % 5 == 0 else "grid_minor"
                )
                lines.append(ViewportOverlayLine(first.x, first.y, second.x, second.y, role))
        return tuple(lines)

    def gizmo_2d(
        self,
        camera: Camera2D,
        target: object,
        width: int,
        height: int,
        mode: str,
    ) -> tuple[ViewportOverlayLine, ...]:
        x = getattr(target, "x", None)
        y = getattr(target, "y", None)
        if not self._numeric(x) or not self._numeric(y):
            return ()
        screen_space = bool(getattr(target, "screen_space", False))
        center = self.world_to_screen_2d(
            camera,
            Vec2(float(x), float(y)),
            width,
            height,
            screen_space=screen_space,
        )
        length = 52.0
        if mode == "rotate":
            return (
                ViewportOverlayLine(
                    center.x - 24.0, center.y - 24.0,
                    center.x + 24.0, center.y - 24.0, "gizmo_rotate"
                ),
                ViewportOverlayLine(
                    center.x + 24.0, center.y - 24.0,
                    center.x + 24.0, center.y + 24.0, "gizmo_rotate"
                ),
                ViewportOverlayLine(
                    center.x + 24.0, center.y + 24.0,
                    center.x - 24.0, center.y + 24.0, "gizmo_rotate"
                ),
                ViewportOverlayLine(
                    center.x - 24.0, center.y + 24.0,
                    center.x - 24.0, center.y - 24.0, "gizmo_rotate"
                ),
            )
        if mode == "scale":
            return (
                ViewportOverlayLine(center.x, center.y, center.x + length, center.y, "gizmo_x"),
                ViewportOverlayLine(center.x, center.y, center.x, center.y - length, "gizmo_y"),
                ViewportOverlayLine(
                    center.x + length - 5.0, center.y - 5.0,
                    center.x + length + 5.0, center.y + 5.0, "gizmo_scale"
                ),
                ViewportOverlayLine(
                    center.x - 5.0, center.y - length - 5.0,
                    center.x + 5.0, center.y - length + 5.0, "gizmo_scale"
                ),
            )
        return (
            ViewportOverlayLine(center.x, center.y, center.x + length, center.y, "gizmo_x"),
            ViewportOverlayLine(center.x, center.y, center.x, center.y - length, "gizmo_y"),
        )

    def gizmo_3d(
        self,
        camera: Camera3D,
        target: object,
        width: int,
        height: int,
        spacing: float,
        mode: str,
    ) -> tuple[ViewportOverlayLine, ...]:
        position = getattr(target, "position", None)
        if not isinstance(position, Vec3):
            return ()
        center = self.project_3d(camera, position, width, height)
        if center is None:
            return ()
        distance = max((position - camera.position).length, 1.0)
        world_length = max(spacing, distance * 0.12)
        axes = (
            (Vec3(world_length, 0.0, 0.0), "gizmo_x"),
            (Vec3(0.0, world_length, 0.0), "gizmo_y"),
            (Vec3(0.0, 0.0, world_length), "gizmo_z"),
        )
        lines: list[ViewportOverlayLine] = []
        for delta, role in axes:
            endpoint = self.project_3d(camera, position + delta, width, height)
            if endpoint is not None:
                lines.append(ViewportOverlayLine(center.x, center.y, endpoint.x, endpoint.y, role))
        if mode == "rotate" and lines:
            lines.append(
                ViewportOverlayLine(
                    center.x - 18.0, center.y,
                    center.x + 18.0, center.y, "gizmo_rotate"
                )
            )
        return tuple(lines)

    @staticmethod
    def world_to_screen_2d(
        camera: Camera2D,
        point: Vec2,
        width: int,
        height: int,
        *,
        screen_space: bool = False,
    ) -> Vec2:
        if screen_space:
            centered_x = point.x
            centered_y = point.y
        else:
            centered_x = (point.x - camera.x) * camera.safe_zoom
            centered_y = (point.y - camera.y) * camera.safe_zoom
        return Vec2(width * 0.5 + centered_x, height * 0.5 - centered_y)

    def project_3d(
        self,
        camera: Camera3D,
        point: Vec3,
        width: int,
        height: int,
    ) -> Vec2 | None:
        width = self._positive_int(width, "viewport width")
        height = self._positive_int(height, "viewport height")
        relative = point - camera.position
        depth = self._dot(relative, camera.forward)
        if depth <= max(float(camera.near), 1e-6) or depth > float(camera.far):
            return None
        tan_half = math.tan(math.radians(float(camera.fov)) * 0.5)
        if tan_half <= 0.0:
            return None
        aspect = width / height
        x_camera = self._dot(relative, camera.right)
        y_camera = self._dot(relative, camera.up.normalized())
        ndc_x = x_camera / (depth * tan_half * aspect)
        ndc_y = y_camera / (depth * tan_half)
        if not math.isfinite(ndc_x) or not math.isfinite(ndc_y):
            return None
        return Vec2((ndc_x + 1.0) * 0.5 * width, (1.0 - ndc_y) * 0.5 * height)

    @classmethod
    def _adaptive_spacing(cls, zoom: float, base_spacing: float, min_pixels: float) -> float:
        zoom = cls._positive_number(zoom, "camera zoom")
        spacing = cls._positive_number(base_spacing, "grid spacing")
        min_pixels = cls._positive_number(min_pixels, "minimum grid pixels")
        while spacing * zoom < min_pixels:
            spacing *= 2.0
        return spacing

    @staticmethod
    def _dot(left: Vec3, right: Vec3) -> float:
        return left.x * right.x + left.y * right.y + left.z * right.z

    @staticmethod
    def _numeric(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _positive_number(cls, value: float, label: str) -> float:
        if not cls._numeric(value):
            raise TypeError(f"{label} must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"{label} must be finite and greater than zero")
        return numeric

    @staticmethod
    def _positive_int(value: int, label: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{label} must be an integer")
        if value <= 0:
            raise ValueError(f"{label} must be greater than zero")
        return value
