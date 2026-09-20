from __future__ import annotations

import math
from typing import Any

from .editor_authoring import EditorMultiGizmoResult
from .editor_creator_frontend21 import EditorCreatorFrontendController21, TkCreatorEditorApp21
from .editor_viewport import EditorViewportController, ViewportPick
from .graphics.camera import Camera2D
from .graphics.camera3d import Camera3D
from .math.types import Vec3


class EditorProductionViewportController21(EditorCreatorFrontendController21):
    """Creator front-end with persistent 2D/3D editor-camera interaction.

    The low-level viewport controller is rebound whenever multi-scene authoring replaces the
    workspace inspector. Picking is mirrored back through the creator selection model, and
    pointer translation uses the grouped creator gizmo path so multi-selection and Ctrl+Z stay
    coherent instead of creating an unrelated legacy history stream.
    """

    def __init__(
        self,
        *args: Any,
        camera_2d: Camera2D | None = None,
        camera_3d: Camera3D | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.camera_2d = camera_2d or Camera2D()
        self.camera_3d = camera_3d or Camera3D()
        self._viewport_bound_inspector: object | None = None
        self._viewport_controller: EditorViewportController | None = None

    @property
    def viewport_controller(self) -> EditorViewportController:
        inspector = self.workspace.inspector
        if self._viewport_controller is None or self._viewport_bound_inspector is not inspector:
            self._viewport_controller = EditorViewportController(self.workspace)
            self._viewport_bound_inspector = inspector
        return self._viewport_controller

    def viewport_pick(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> ViewportPick | None:
        """Pick in the active engine mode and synchronize creator multi-selection."""

        if self.workspace.viewport.mode == "2d":
            hit = self.viewport_controller.pick_2d(
                self.camera_2d,
                x,
                y,
                width,
                height,
                select=False,
            )
        else:
            hit = self.viewport_controller.pick_3d(
                self.camera_3d,
                x,
                y,
                width,
                height,
                select=False,
            )
        if hit is None:
            self.select(None)
            self._status = "Viewport selection cleared"
            return None
        self.select(hit.target_key)
        self._status = f"Viewport selected {hit.target_key}"
        return hit

    def viewport_translate_selection(
        self,
        dx_pixels: float,
        dy_pixels: float,
        viewport_height: float,
    ) -> tuple[EditorMultiGizmoResult, ...]:
        """Translate the creator selection from a viewport drag as grouped gizmo edits."""

        viewport = self.workspace.viewport
        if viewport.gizmo != "translate":
            raise RuntimeError("pointer translation requires the translate gizmo")
        dx = self.viewport_controller._number(dx_pixels, "pointer delta x")
        dy = self.viewport_controller._number(dy_pixels, "pointer delta y")
        snap = viewport.translation_snap if viewport.snap_enabled else None

        if viewport.mode == "2d":
            zoom = self.viewport_controller._positive_number(
                self.camera_2d.safe_zoom,
                "camera zoom",
            )
            delta = Vec3(dx / zoom, -dy / zoom, 0.0)
        else:
            target = self.authoring.components.selection.primary_target
            if target is None:
                raise RuntimeError("no viewport target selected")
            position = getattr(target, "position", None)
            if not isinstance(position, Vec3):
                raise TypeError("selected target does not expose a 3D position")
            height = self.viewport_controller._positive_number(
                viewport_height,
                "viewport height",
            )
            camera = self.camera_3d
            depth = self.viewport_controller._dot(position - camera.position, camera.forward)
            depth = self.viewport_controller._positive_number(depth, "drag depth")
            world_per_pixel = (
                2.0 * depth * math.tan(math.radians(camera.fov) * 0.5)
            ) / height
            delta = camera.right * (dx * world_per_pixel) + camera.up.normalized() * (
                -dy * world_per_pixel
            )

        results: list[EditorMultiGizmoResult] = []
        axes = (("x", delta.x), ("y", delta.y))
        if viewport.mode == "3d":
            axes = (*axes, ("z", delta.z))
        for axis, amount in axes:
            if abs(amount) <= 1e-12:
                continue
            results.append(
                self.authoring.components.apply_gizmo(
                    "translate",
                    axis,
                    amount,
                    snap=snap,
                )
            )
        self._status = f"Viewport translated {self.selection_count} item(s)"
        return tuple(results)

    def viewport_pan(
        self,
        dx_pixels: float,
        dy_pixels: float,
        viewport_height: float,
    ) -> object:
        """Pan the persistent editor camera for the active engine mode."""

        if self.workspace.viewport.mode == "2d":
            camera: object = self.viewport_controller.pan_camera_2d(
                self.camera_2d,
                dx_pixels,
                dy_pixels,
            )
        else:
            camera = self.viewport_controller.pan_camera_3d(
                self.camera_3d,
                dx_pixels,
                dy_pixels,
                viewport_height,
            )
        self._status = "Viewport camera panned"
        return camera

    def viewport_zoom(self, steps: float) -> object:
        """Zoom 2D or dolly the 3D editor camera from wheel/trackpad steps."""

        steps = self.viewport_controller._number(steps, "zoom steps")
        if self.workspace.viewport.mode == "2d":
            camera: object = self.viewport_controller.zoom_camera_2d(self.camera_2d, steps)
            self._status = f"Viewport zoom: {self.camera_2d.zoom:.2f}x"
            return camera

        distance = (self.camera_3d.target - self.camera_3d.position).length
        unit = max(0.25, distance * 0.1)
        camera = self.viewport_controller.dolly_camera_3d(self.camera_3d, steps * unit)
        self._status = "Viewport camera dolly"
        return camera


class TkProductionViewportEditorApp21(TkCreatorEditorApp21):
    """Tk creator shell with direct picking, translation and camera navigation bindings."""

    controller: EditorProductionViewportController21

    def __init__(self, controller: EditorProductionViewportController21, **kwargs: Any) -> None:
        self._viewport_drag: tuple[float, float] | None = None
        self._viewport_pan: tuple[float, float] | None = None
        super().__init__(controller, **kwargs)

    def _build(self) -> None:
        super()._build()
        self.viewport_label.bind("<Button-1>", self._viewport_primary_press)
        self.viewport_label.bind("<B1-Motion>", self._viewport_primary_drag)
        self.viewport_label.bind("<ButtonRelease-1>", self._viewport_primary_release)
        self.viewport_label.bind("<Button-2>", self._viewport_pan_press)
        self.viewport_label.bind("<B2-Motion>", self._viewport_pan_drag)
        self.viewport_label.bind("<ButtonRelease-2>", self._viewport_pan_release)
        self.viewport_label.bind("<MouseWheel>", self._viewport_wheel)
        self.viewport_label.bind("<Button-4>", self._viewport_wheel)
        self.viewport_label.bind("<Button-5>", self._viewport_wheel)

    def _viewport_size(self) -> tuple[int, int]:
        return (max(1, self.viewport_label.winfo_width()), max(1, self.viewport_label.winfo_height()))

    def _viewport_primary_press(self, event: Any) -> None:
        self._viewport_drag = (float(event.x), float(event.y))
        width, height = self._viewport_size()
        try:
            self.controller.viewport_pick(event.x, event.y, width, height)
        except (KeyError, LookupError, TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))

    def _viewport_primary_drag(self, event: Any) -> None:
        previous = self._viewport_drag
        self._viewport_drag = (float(event.x), float(event.y))
        if previous is None or self.controller.workspace.viewport.gizmo != "translate":
            return
        _, height = self._viewport_size()
        try:
            self.controller.viewport_translate_selection(
                float(event.x) - previous[0],
                float(event.y) - previous[1],
                height,
            )
        except (KeyError, LookupError, TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))

    def _viewport_primary_release(self, _event: Any = None) -> None:
        self._viewport_drag = None

    def _viewport_pan_press(self, event: Any) -> None:
        self._viewport_pan = (float(event.x), float(event.y))

    def _viewport_pan_drag(self, event: Any) -> None:
        previous = self._viewport_pan
        self._viewport_pan = (float(event.x), float(event.y))
        if previous is None:
            return
        _, height = self._viewport_size()
        try:
            self.controller.viewport_pan(
                float(event.x) - previous[0],
                float(event.y) - previous[1],
                height,
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))

    def _viewport_pan_release(self, _event: Any = None) -> None:
        self._viewport_pan = None

    def _viewport_wheel(self, event: Any) -> str:
        delta = float(getattr(event, "delta", 0.0))
        if delta:
            steps = delta / 120.0
        else:
            button = int(getattr(event, "num", 0))
            steps = 1.0 if button == 4 else -1.0 if button == 5 else 0.0
        if steps:
            try:
                self.controller.viewport_zoom(steps)
            except (TypeError, ValueError, RuntimeError) as exc:
                self.status_var.set(str(exc))
        return "break"
