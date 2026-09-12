from __future__ import annotations

import math
from dataclasses import dataclass

from .editor_gizmo import EditorTransformGizmo, GizmoApplyResult
from .graphics.camera3d import Camera3D
from .graphics.mesh import Mesh3D
from .math.types import Vec3


@dataclass(frozen=True, slots=True)
class ViewportRay:
    """World-space ray produced from a viewport pointer position."""

    origin: Vec3
    direction: Vec3


@dataclass(frozen=True, slots=True)
class ViewportPick:
    """One resolved viewport hit sorted by nearest distance."""

    target_key: str
    distance: float
    world_position: Vec3


class EditorViewportController:
    """Toolkit-independent viewport picking and direct transform manipulation.

    Pointer coordinates are expressed in framebuffer pixels with ``(0, 0)`` at the
    top-left. 3D picking uses camera-derived world rays and conservative mesh bounding
    spheres, which keeps the controller independent from a particular GPU backend while
    remaining fast enough for editor interaction. Selected objects can then be dragged
    in the camera plane through the existing ``EditorTransformGizmo`` history path.
    """

    def __init__(self, workspace: object) -> None:
        inspector = getattr(workspace, "inspector", None)
        viewport = getattr(workspace, "viewport", None)
        if inspector is None or viewport is None:
            raise TypeError("workspace must expose inspector and viewport")
        self.workspace = workspace
        self.inspector = inspector
        self.gizmo = EditorTransformGizmo(inspector)

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
        """Pick the nearest visible ``Mesh3D`` using conservative world bounds."""
        ray = self.ray_from_screen(camera, x, y, width, height)
        best: ViewportPick | None = None
        for target in self.inspector.scene.objects:
            if not isinstance(target, Mesh3D) or not target.enabled or not target.visible:
                continue
            radius = self._mesh_radius(target)
            distance = self._ray_sphere(ray, target.position, radius)
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
        """Translate the current 3D selection in the camera plane from a pointer delta.

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
        delta = camera.right * (dx * world_per_pixel) + camera.up.normalized() * (-dy * world_per_pixel)

        viewport = self.workspace.viewport
        results: list[GizmoApplyResult] = []
        for axis, amount in (("x", delta.x), ("y", delta.y), ("z", delta.z)):
            if abs(amount) > 1e-12:
                results.append(self.gizmo.apply_viewport(viewport, axis, amount, target=target))
        return tuple(results)

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
