from __future__ import annotations

import math
from dataclasses import dataclass

from .editor_gizmo import EditorTransformGizmo, GizmoApplyResult
from .graphics.camera import Camera2D
from .graphics.camera3d import Camera3D
from .graphics.mesh import Mesh3D
from .graphics.primitives import Cube3D, Rectangle2D, Sprite2D
from .math.types import Vec2, Vec3


@dataclass(frozen=True, slots=True)
class ViewportRay:
    """World-space ray produced from a viewport pointer position."""

    origin: Vec3
    direction: Vec3


@dataclass(frozen=True, slots=True)
class ViewportPick:
    """One resolved viewport hit.

    ``distance`` is the ray distance for 3D hits and ``0.0`` for 2D hits, where visual
    stacking order (layer, then scene order) determines the winning target.
    """

    target_key: str
    distance: float
    world_position: Vec3


class EditorViewportController:
    """Toolkit-independent production viewport interaction controller.

    Pointer coordinates use framebuffer pixels with ``(0, 0)`` at the top-left. The
    controller keeps editor interaction independent from a specific GUI or GPU backend:
    2D picking mirrors the renderer's centered orthographic camera convention, while 3D
    picking uses camera-derived world rays and conservative object bounds. Transform
    mutations still flow through :class:`EditorTransformGizmo`, so the normal inspector
    history, snapping and undo/redo contracts remain authoritative.
    """

    def __init__(self, workspace: object) -> None:
        inspector = getattr(workspace, "inspector", None)
        viewport = getattr(workspace, "viewport", None)
        if inspector is None or viewport is None:
            raise TypeError("workspace must expose inspector and viewport")
        self.workspace = workspace
        self._gizmo_inspector: object | None = None
        self._gizmo: EditorTransformGizmo | None = None

    @property
    def inspector(self):
        """Return the current workspace inspector, including after scene switches."""

        return self.workspace.inspector

    @property
    def gizmo(self) -> EditorTransformGizmo:
        """Keep transform history bound to the current scene inspector."""

        inspector = self.inspector
        if self._gizmo is None or self._gizmo_inspector is not inspector:
            self._gizmo = EditorTransformGizmo(inspector)
            self._gizmo_inspector = inspector
        return self._gizmo

    def screen_to_world_2d(
        self,
        camera: Camera2D,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        screen_space: bool = False,
    ) -> Vec2:
        """Convert a framebuffer pointer to the renderer's centered 2D coordinate space."""

        width = self._positive_number(width, "viewport width")
        height = self._positive_number(height, "viewport height")
        x = self._number(x, "pointer x")
        y = self._number(y, "pointer y")
        centered_x = x - width * 0.5
        centered_y = height * 0.5 - y
        if screen_space:
            return Vec2(centered_x, centered_y)
        zoom = self._positive_number(camera.safe_zoom, "camera zoom")
        return Vec2(camera.x + centered_x / zoom, camera.y + centered_y / zoom)

    def world_to_screen_2d(
        self,
        camera: Camera2D,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        screen_space: bool = False,
    ) -> Vec2:
        """Project a 2D world/screen-space point back to framebuffer pixels."""

        width = self._positive_number(width, "viewport width")
        height = self._positive_number(height, "viewport height")
        x = self._number(x, "world x")
        y = self._number(y, "world y")
        if screen_space:
            centered_x = x
            centered_y = y
        else:
            zoom = self._positive_number(camera.safe_zoom, "camera zoom")
            centered_x = (x - camera.x) * zoom
            centered_y = (y - camera.y) * zoom
        return Vec2(width * 0.5 + centered_x, height * 0.5 - centered_y)

    def pick_2d(
        self,
        camera: Camera2D,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        select: bool = True,
    ) -> ViewportPick | None:
        """Pick the visually top-most bounded 2D primitive at a framebuffer position.

        Rectangle bounds are always available. Sprite bounds are pickable when explicit
        ``width`` and ``height`` are supplied; implicit texture-size sprites intentionally
        remain unpickable here rather than causing hidden image I/O in editor interaction.
        Rotation is handled by inverse-transforming the pointer into local object space.
        """

        world_point = self.screen_to_world_2d(camera, x, y, width, height)
        screen_point = self.screen_to_world_2d(
            camera, x, y, width, height, screen_space=True
        )
        indexed = list(enumerate(self.inspector.scene.objects))
        indexed.sort(
            key=lambda item: (int(getattr(item[1], "layer", 0)), item[0]),
            reverse=True,
        )
        for _, target in indexed:
            if not getattr(target, "enabled", True) or not getattr(target, "visible", True):
                continue
            bounds = self._bounds_2d(target)
            if bounds is None:
                continue
            point = screen_point if bool(getattr(target, "screen_space", False)) else world_point
            center_x = float(target.x)
            center_y = float(target.y)
            rotation = float(getattr(target, "rotation", 0.0))
            if not self._point_in_rotated_rect(
                point,
                center_x,
                center_y,
                bounds[0],
                bounds[1],
                rotation,
            ):
                continue
            key = self.inspector.key_for(target)
            hit = ViewportPick(key, 0.0, Vec3(point.x, point.y, 0.0))
            if select:
                self.inspector.select(key)
            return hit
        if select:
            self.inspector.select(None)
        return None

    def drag_selected_2d(
        self,
        camera: Camera2D,
        dx_pixels: float,
        dy_pixels: float,
    ) -> tuple[GizmoApplyResult, ...]:
        """Translate the selected 2D target by a pointer delta with viewport snapping."""

        target = self.inspector.selected_target
        if target is None:
            raise RuntimeError("no viewport target selected")
        if self.workspace.viewport.gizmo != "translate":
            raise RuntimeError("2D pointer translation requires the translate gizmo")
        dx = self._number(dx_pixels, "pointer delta x")
        dy = self._number(dy_pixels, "pointer delta y")
        zoom = self._positive_number(camera.safe_zoom, "camera zoom")
        world_dx = dx / zoom
        world_dy = -dy / zoom
        results: list[GizmoApplyResult] = []
        if abs(world_dx) > 1e-12:
            results.append(
                self.gizmo.apply_viewport(self.workspace.viewport, "x", world_dx, target=target)
            )
        if abs(world_dy) > 1e-12:
            results.append(
                self.gizmo.apply_viewport(self.workspace.viewport, "y", world_dy, target=target)
            )
        return tuple(results)

    def pan_camera_2d(self, camera: Camera2D, dx_pixels: float, dy_pixels: float) -> Camera2D:
        """Pan a 2D camera so scene content follows the pointer drag."""

        dx = self._number(dx_pixels, "pointer delta x")
        dy = self._number(dy_pixels, "pointer delta y")
        zoom = self._positive_number(camera.safe_zoom, "camera zoom")
        camera.move(-dx / zoom, dy / zoom)
        return camera

    def zoom_camera_2d(
        self,
        camera: Camera2D,
        steps: float,
        *,
        factor: float = 1.15,
        min_zoom: float = 0.05,
        max_zoom: float = 64.0,
    ) -> Camera2D:
        """Apply bounded exponential zoom suitable for wheel/trackpad input."""

        steps = self._number(steps, "zoom steps")
        factor = self._positive_number(factor, "zoom factor")
        min_zoom = self._positive_number(min_zoom, "minimum zoom")
        max_zoom = self._positive_number(max_zoom, "maximum zoom")
        if factor <= 1.0:
            raise ValueError("zoom factor must be greater than 1")
        if min_zoom > max_zoom:
            raise ValueError("minimum zoom cannot exceed maximum zoom")
        current = self._positive_number(camera.safe_zoom, "camera zoom")
        camera.zoom = min(max_zoom, max(min_zoom, current * (factor**steps)))
        return camera

    def ray_from_screen(
        self,
        camera: Camera3D,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> ViewportRay:
        """Build a perspective world ray from a framebuffer-space pointer."""

        width = self._positive_number(width, "viewport width")
        height = self._positive_number(height, "viewport height")
        x = self._number(x, "pointer x")
        y = self._number(y, "pointer y")
        if camera.fov <= 0.0 or camera.fov >= 180.0:
            raise ValueError("camera fov must be between 0 and 180 degrees")

        ndc_x = (2.0 * x / width) - 1.0
        ndc_y = 1.0 - (2.0 * y / height)
        tan_half = math.tan(math.radians(camera.fov) * 0.5)
        aspect = width / height
        forward = camera.forward
        right = camera.right
        up = camera.up.normalized()
        direction = (
            forward
            + right * (ndc_x * tan_half * aspect)
            + up * (ndc_y * tan_half)
        ).normalized()
        return ViewportRay(camera.position, direction)

    def pick_3d(
        self,
        camera: Camera3D,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        select: bool = True,
    ) -> ViewportPick | None:
        """Pick the nearest visible mesh/cube using conservative world bounds."""

        ray = self.ray_from_screen(camera, x, y, width, height)
        best: ViewportPick | None = None
        for target in self.inspector.scene.objects:
            if not getattr(target, "enabled", True) or not getattr(target, "visible", True):
                continue
            if isinstance(target, Mesh3D):
                center = target.position
                radius = self._mesh_radius(target)
            elif isinstance(target, Cube3D):
                center = target.position
                radius = max(abs(float(target.size)) * math.sqrt(3.0) * 0.5, 1e-6)
            else:
                continue
            distance = self._ray_sphere(ray, center, radius)
            if distance is None or distance < camera.near or distance > camera.far:
                continue
            hit = ViewportPick(
                self.inspector.key_for(target),
                distance,
                ray.origin + ray.direction * distance,
            )
            if best is None or hit.distance < best.distance:
                best = hit
        if select:
            self.inspector.select(None if best is None else best.target_key)
        return best

    def drag_selected_3d(
        self,
        camera: Camera3D,
        dx_pixels: float,
        dy_pixels: float,
        viewport_height: float,
        *,
        depth: float | None = None,
    ) -> tuple[GizmoApplyResult, ...]:
        """Manipulate the current 3D selection in the camera plane from a pointer delta.

        The pixel delta is converted to world units at the selected object's camera depth.
        Each axis mutation goes through the normal gizmo/inspector path, so undo/redo stays
        authoritative. The returned tuple contains only non-zero axis edits.
        """

        target = self.inspector.selected_target
        if target is None:
            raise RuntimeError("no viewport target selected")
        position = getattr(target, "position", None)
        if not isinstance(position, Vec3):
            raise TypeError("selected target does not expose a 3D position")
        height = self._positive_number(viewport_height, "viewport height")
        dx = self._number(dx_pixels, "pointer delta x")
        dy = self._number(dy_pixels, "pointer delta y")

        if depth is None:
            depth = self._dot(position - camera.position, camera.forward)
        depth = self._positive_number(depth, "drag depth")
        world_per_pixel = (2.0 * depth * math.tan(math.radians(camera.fov) * 0.5)) / height
        delta = camera.right * (dx * world_per_pixel) + camera.up.normalized() * (
            -dy * world_per_pixel
        )

        viewport = self.workspace.viewport
        results: list[GizmoApplyResult] = []
        for axis, amount in (("x", delta.x), ("y", delta.y), ("z", delta.z)):
            if abs(amount) > 1e-12:
                results.append(self.gizmo.apply_viewport(viewport, axis, amount, target=target))
        return tuple(results)

    def pan_camera_3d(
        self,
        camera: Camera3D,
        dx_pixels: float,
        dy_pixels: float,
        viewport_height: float,
        *,
        depth: float | None = None,
    ) -> Camera3D:
        """Pan camera position and target in the current view plane."""

        height = self._positive_number(viewport_height, "viewport height")
        dx = self._number(dx_pixels, "pointer delta x")
        dy = self._number(dy_pixels, "pointer delta y")
        if depth is None:
            depth = (camera.target - camera.position).length
        depth = self._positive_number(depth, "camera pan depth")
        world_per_pixel = (2.0 * depth * math.tan(math.radians(camera.fov) * 0.5)) / height
        delta = camera.right * (-dx * world_per_pixel) + camera.up.normalized() * (
            dy * world_per_pixel
        )
        camera.move(delta.x, delta.y, delta.z)
        return camera

    def dolly_camera_3d(self, camera: Camera3D, distance: float) -> Camera3D:
        """Move a 3D camera along its local forward axis while preserving orientation."""

        distance = self._number(distance, "dolly distance")
        camera.move_local(forward=distance)
        return camera

    @staticmethod
    def _bounds_2d(target: object) -> tuple[float, float] | None:
        if not isinstance(target, (Rectangle2D, Sprite2D)):
            return None
        if isinstance(target, Sprite2D) and (target.width is None or target.height is None):
            return None
        width = abs(float(target.width))
        height = abs(float(target.height))
        if width <= 0.0 or height <= 0.0:
            return None
        return (width, height)

    @staticmethod
    def _point_in_rotated_rect(
        point: Vec2,
        center_x: float,
        center_y: float,
        width: float,
        height: float,
        rotation_degrees: float,
    ) -> bool:
        angle = math.radians(-rotation_degrees)
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        dx = point.x - center_x
        dy = point.y - center_y
        local_x = cos_angle * dx - sin_angle * dy
        local_y = sin_angle * dx + cos_angle * dy
        return abs(local_x) <= width * 0.5 and abs(local_y) <= height * 0.5

    @staticmethod
    def _mesh_radius(mesh: Mesh3D) -> float:
        vertices = mesh.mesh.vertices
        local_radius = max(
            math.sqrt(float(x * x + y * y + z * z))
            for x, y, z in vertices
        )
        scale = max(abs(mesh.scale.x), abs(mesh.scale.y), abs(mesh.scale.z))
        return max(local_radius * scale, 1e-6)

    @staticmethod
    def _ray_sphere(ray: ViewportRay, center: Vec3, radius: float) -> float | None:
        offset = ray.origin - center
        b = EditorViewportController._dot(offset, ray.direction)
        c = EditorViewportController._dot(offset, offset) - radius * radius
        discriminant = b * b - c
        if discriminant < 0.0:
            return None
        root = math.sqrt(discriminant)
        near = -b - root
        far = -b + root
        if near >= 0.0:
            return near
        if far >= 0.0:
            return far
        return None

    @staticmethod
    def _dot(left: Vec3, right: Vec3) -> float:
        return left.x * right.x + left.y * right.y + left.z * right.z

    @staticmethod
    def _number(value: float, label: str) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(f"{label} must be numeric")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"{label} must be finite")
        return value

    @classmethod
    def _positive_number(cls, value: float, label: str) -> float:
        value = cls._number(value, label)
        if value <= 0.0:
            raise ValueError(f"{label} must be greater than zero")
        return value
