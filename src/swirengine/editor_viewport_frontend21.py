from __future__ import annotations

import base64
import math
from typing import Any

from .editor_authoring import EditorMultiGizmoResult
from .editor_creator_frontend21 import EditorCreatorFrontendController21, TkCreatorEditorApp21
from .editor_viewport import EditorViewportController, ViewportPick
from .editor_viewport_overlay import EditorViewportOverlay, ViewportOverlayFrame
from .graphics.camera import Camera2D
from .graphics.camera3d import Camera3D
from .math.types import Vec3

_VIEWPORT_AXES = {"all", "x", "y", "z"}


class EditorProductionViewportController21(EditorCreatorFrontendController21):
    """Creator front-end with persistent 2D/3D editor-camera interaction.

    The low-level viewport controller is rebound whenever multi-scene authoring replaces the
    workspace inspector. Picking is mirrored back through the creator selection model, pointer
    transforms use grouped creator gizmo history, and grid/gizmo overlays are generated through a
    toolkit-independent model so desktop/web shells can present the same interaction state.
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
        self._viewport_axis = "all"
        self._overlay = EditorViewportOverlay()

    @property
    def viewport_controller(self) -> EditorViewportController:
        inspector = self.workspace.inspector
        if self._viewport_controller is None or self._viewport_bound_inspector is not inspector:
            self._viewport_controller = EditorViewportController(self.workspace)
            self._viewport_bound_inspector = inspector
        return self._viewport_controller

    @property
    def viewport_axis(self) -> str:
        return self._viewport_axis

    def set_viewport_axis(self, axis: str) -> str:
        normalized = axis.strip().lower()
        if normalized not in _VIEWPORT_AXES:
            raise ValueError(f"unsupported viewport axis {axis!r}")
        self._viewport_axis = normalized
        self._status = f"Viewport axis: {normalized.upper()}"
        return normalized

    def set_grid_visible(self, visible: bool) -> bool:
        if not isinstance(visible, bool):
            raise TypeError("grid visibility must be boolean")
        self.workspace.configure_viewport(grid_visible=visible)
        self._status = "Viewport grid shown" if visible else "Viewport grid hidden"
        return visible

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

    def viewport_transform_selection(
        self,
        dx_pixels: float,
        dy_pixels: float,
        viewport_height: float,
    ) -> tuple[EditorMultiGizmoResult, ...]:
        """Apply the active Move/Rotate/Scale gizmo from one viewport pointer drag."""

        viewport = self.workspace.viewport
        mode = viewport.gizmo
        if mode == "none":
            raise RuntimeError("viewport gizmo is disabled")
        dx = self.viewport_controller._number(dx_pixels, "pointer delta x")
        dy = self.viewport_controller._number(dy_pixels, "pointer delta y")
        if abs(dx) <= 1e-12 and abs(dy) <= 1e-12:
            return ()

        snap = None
        if viewport.snap_enabled:
            snap = {
                "translate": viewport.translation_snap,
                "rotate": viewport.rotation_snap,
                "scale": viewport.scale_snap,
            }[mode]

        if mode == "translate":
            deltas = self._translation_deltas(dx, dy, viewport_height)
        elif mode == "rotate":
            deltas = self._rotation_deltas(dx, dy)
        else:
            deltas = self._scale_deltas(dx, dy)

        results: list[EditorMultiGizmoResult] = []
        for axis, amount in deltas:
            if abs(amount) <= 1e-12:
                continue
            results.append(
                self.authoring.components.apply_gizmo(
                    mode,
                    axis,
                    amount,
                    snap=snap,
                )
            )
        self._status = (
            f"Viewport {mode} {self.selection_count} item(s)"
            if results
            else f"Viewport {mode}: no transform delta"
        )
        return tuple(results)

    def viewport_translate_selection(
        self,
        dx_pixels: float,
        dy_pixels: float,
        viewport_height: float,
    ) -> tuple[EditorMultiGizmoResult, ...]:
        """Backwards-compatible translation entry point for existing creator integrations."""

        if self.workspace.viewport.gizmo != "translate":
            raise RuntimeError("pointer translation requires the translate gizmo")
        return self.viewport_transform_selection(dx_pixels, dy_pixels, viewport_height)

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

    def viewport_orbit(
        self,
        dx_pixels: float,
        dy_pixels: float,
        *,
        sensitivity: float = 0.35,
    ) -> Camera3D:
        """Orbit the 3D editor camera around its target with bounded pitch."""

        if self.workspace.viewport.mode != "3d":
            raise RuntimeError("camera orbit is available only in 3D mode")
        dx = self.viewport_controller._number(dx_pixels, "pointer delta x")
        dy = self.viewport_controller._number(dy_pixels, "pointer delta y")
        sensitivity = self.viewport_controller._positive_number(
            sensitivity, "orbit sensitivity"
        )
        camera = self.camera_3d
        offset = camera.position - camera.target
        radius = self.viewport_controller._positive_number(offset.length, "orbit radius")
        yaw = math.atan2(offset.x, offset.z)
        pitch = math.asin(max(-1.0, min(1.0, offset.y / radius)))
        yaw -= math.radians(dx * sensitivity)
        pitch += math.radians(dy * sensitivity)
        limit = math.radians(89.0)
        pitch = max(-limit, min(limit, pitch))
        cos_pitch = math.cos(pitch)
        camera.position = camera.target + Vec3(
            radius * math.sin(yaw) * cos_pitch,
            radius * math.sin(pitch),
            radius * math.cos(yaw) * cos_pitch,
        )
        self._status = "Viewport camera orbited"
        return camera

    def viewport_overlay(self, width: int, height: int) -> ViewportOverlayFrame:
        """Return deterministic grid/gizmo overlay geometry for the active viewport."""

        viewport = self.workspace.viewport
        return self._overlay.build(
            mode=viewport.mode,
            camera_2d=self.camera_2d,
            camera_3d=self.camera_3d,
            width=width,
            height=height,
            grid_visible=viewport.grid_visible,
            grid_spacing=viewport.translation_snap,
            selected_target=self.authoring.components.selection.primary_target,
            gizmo=viewport.gizmo,
        )

    def _translation_deltas(
        self,
        dx: float,
        dy: float,
        viewport_height: float,
    ) -> tuple[tuple[str, float], ...]:
        viewport = self.workspace.viewport
        if viewport.mode == "2d":
            if self._viewport_axis == "z":
                raise ValueError("2D translation supports only X/Y axes")
            zoom = self.viewport_controller._positive_number(
                self.camera_2d.safe_zoom,
                "camera zoom",
            )
            values = {"x": dx / zoom, "y": -dy / zoom}
            if self._viewport_axis == "all":
                return (("x", values["x"]), ("y", values["y"]))
            return ((self._viewport_axis, values[self._viewport_axis]),)

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
        values = {"x": delta.x, "y": delta.y, "z": delta.z}
        if self._viewport_axis == "all":
            return tuple((axis, values[axis]) for axis in ("x", "y", "z"))
        return ((self._viewport_axis, values[self._viewport_axis]),)

    def _rotation_deltas(self, dx: float, dy: float) -> tuple[tuple[str, float], ...]:
        sensitivity = 0.5
        if self.workspace.viewport.mode == "2d":
            if self._viewport_axis not in {"all", "z"}:
                raise ValueError("2D rotation uses the Z axis")
            return (("z", (dx - dy) * sensitivity),)
        if self._viewport_axis == "all":
            return (("x", -dy * sensitivity), ("y", dx * sensitivity))
        return ((self._viewport_axis, (dx - dy) * sensitivity),)

    def _scale_deltas(self, dx: float, dy: float) -> tuple[tuple[str, float], ...]:
        amount = (dx - dy) * 0.01
        if self.workspace.viewport.mode == "2d":
            if self._viewport_axis == "z":
                raise ValueError("2D scale does not use the Z axis")
            target = self.authoring.components.selection.primary_target
            width = None if target is None else getattr(target, "width", None)
            height = None if target is None else getattr(target, "height", None)
            has_dimensions = all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in (width, height)
            )
            if self._viewport_axis == "all" and has_dimensions:
                return (("x", amount), ("y", amount))
        return ((self._viewport_axis, amount),)


class TkProductionViewportEditorApp21(TkCreatorEditorApp21):
    """Tk creator shell with viewport picking, gizmos, grid overlays and camera navigation."""

    controller: EditorProductionViewportController21

    def __init__(self, controller: EditorProductionViewportController21, **kwargs: Any) -> None:
        self._viewport_drag: tuple[float, float] | None = None
        self._viewport_pan: tuple[float, float] | None = None
        self._viewport_orbit: tuple[float, float] | None = None
        super().__init__(controller, **kwargs)

    def _build(self) -> None:
        super()._build()
        parent = self.viewport_label.master
        self.viewport_label.destroy()
        self.viewport_canvas = self.tk.Canvas(
            parent,
            background="#07111C",
            highlightthickness=0,
            takefocus=True,
        )
        self.viewport_canvas.pack(fill="both", expand=True)
        self.viewport_label = self.viewport_canvas

        toolbar = self.undo_button.master
        self.ttk.Separator(toolbar, orient="vertical").pack(
            side="left",
            fill="y",
            padx=(10, 8),
        )
        self.grid_var = self.tk.BooleanVar(value=self.controller.workspace.viewport.grid_visible)
        self.ttk.Checkbutton(
            toolbar,
            text="Grid",
            variable=self.grid_var,
            command=self._viewport_grid_toggle,
        ).pack(side="left")
        self.axis_var = self.tk.StringVar(value=self.controller.viewport_axis.upper())
        self.ttk.Label(toolbar, text="Axis").pack(side="left", padx=(10, 4))
        axis_box = self.ttk.Combobox(
            toolbar,
            width=4,
            state="readonly",
            textvariable=self.axis_var,
            values=("ALL", "X", "Y", "Z"),
        )
        axis_box.pack(side="left")
        axis_box.bind("<<ComboboxSelected>>", self._viewport_axis_change)

        self.viewport_label.bind("<Button-1>", self._viewport_primary_press)
        self.viewport_label.bind("<B1-Motion>", self._viewport_primary_drag)
        self.viewport_label.bind("<ButtonRelease-1>", self._viewport_primary_release)
        self.viewport_label.bind("<Button-2>", self._viewport_pan_press)
        self.viewport_label.bind("<B2-Motion>", self._viewport_pan_drag)
        self.viewport_label.bind("<ButtonRelease-2>", self._viewport_pan_release)
        self.viewport_label.bind("<Button-3>", self._viewport_orbit_press)
        self.viewport_label.bind("<B3-Motion>", self._viewport_orbit_drag)
        self.viewport_label.bind("<ButtonRelease-3>", self._viewport_orbit_release)
        self.viewport_label.bind("<MouseWheel>", self._viewport_wheel)
        self.viewport_label.bind("<Button-4>", self._viewport_wheel)
        self.viewport_label.bind("<Button-5>", self._viewport_wheel)

    def _refresh_toolbar(self, frame: Any) -> None:
        super()._refresh_toolbar(frame)
        if hasattr(self, "grid_var"):
            self.grid_var.set(frame.shell.viewport.grid_visible)
        if hasattr(self, "axis_var"):
            self.axis_var.set(self.controller.viewport_axis.upper())

    def _refresh_viewport(self, frame: Any) -> None:
        canvas = self.viewport_canvas
        width, height = self._viewport_size()
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#07111C", outline="")

        has_preview = frame.preview is not None and frame.preview.image is not None
        if has_preview:
            data = base64.b64encode(frame.preview.image.to_ppm()).decode("ascii")
            self._viewport_photo = self.tk.PhotoImage(data=data, format="PPM")
            canvas.create_image(width * 0.5, height * 0.5, image=self._viewport_photo)
        else:
            self._viewport_photo = None

        overlay = self.controller.viewport_overlay(width, height)
        styles = {
            "grid_minor": ("#102B3D", 1),
            "grid_major": ("#19445D", 1),
            "axis_x": ("#3A697F", 1),
            "axis_y": ("#3A697F", 1),
            "axis_z": ("#3A697F", 1),
            "gizmo_x": ("#62E5FF", 2),
            "gizmo_y": ("#0088FF", 2),
            "gizmo_z": ("#B7A7FF", 2),
            "gizmo_rotate": ("#62E5FF", 2),
            "gizmo_scale": ("#F4FAFF", 2),
        }
        for line in overlay.lines:
            color, line_width = styles.get(line.role, ("#8DA8B8", 1))
            canvas.create_line(
                line.x1, line.y1, line.x2, line.y2, fill=color, width=line_width
            )

        if not has_preview:
            selected = "No selection"
            if frame.shell.inspector is not None:
                selected = frame.shell.inspector.type_name
            vp = frame.shell.viewport
            runtime = "Edit"
            if frame.preview is not None:
                runtime = frame.preview.runtime.mode.value.title()
            canvas.create_text(
                width * 0.5,
                height * 0.5,
                text=(
                    f"SwirEngine Viewport ({vp.mode.upper()})\n\n"
                    f"Runtime: {runtime}\nSelected: {selected}\nGizmo: {vp.gizmo}\n"
                    f"Axis: {self.controller.viewport_axis.upper()} · "
                    f"Snap: {'on' if vp.snap_enabled else 'off'} · "
                    f"Grid: {'on' if vp.grid_visible else 'off'}\n\n"
                    "Live renderer framebuffer can be attached through RendererViewportBridge."
                ),
                fill="#8DA8B8",
                justify="center",
            )

    def _viewport_size(self) -> tuple[int, int]:
        return (
            max(1, self.viewport_label.winfo_width()),
            max(1, self.viewport_label.winfo_height()),
        )

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
        if previous is None or self.controller.workspace.viewport.gizmo == "none":
            return
        _, height = self._viewport_size()
        try:
            self.controller.viewport_transform_selection(
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

    def _viewport_orbit_press(self, event: Any) -> None:
        if self.controller.workspace.viewport.mode != "3d":
            self._viewport_orbit = None
            return
        self._viewport_orbit = (float(event.x), float(event.y))

    def _viewport_orbit_drag(self, event: Any) -> None:
        previous = self._viewport_orbit
        self._viewport_orbit = (float(event.x), float(event.y))
        if previous is None:
            return
        try:
            self.controller.viewport_orbit(
                float(event.x) - previous[0],
                float(event.y) - previous[1],
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))

    def _viewport_orbit_release(self, _event: Any = None) -> None:
        self._viewport_orbit = None

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

    def _viewport_grid_toggle(self) -> None:
        try:
            self.controller.set_grid_visible(bool(self.grid_var.get()))
        except (TypeError, ValueError) as exc:
            self.status_var.set(str(exc))

    def _viewport_axis_change(self, _event: Any = None) -> None:
        try:
            self.controller.set_viewport_axis(self.axis_var.get())
        except ValueError as exc:
            self.status_var.set(str(exc))

    def _viewport_axis_shortcut(self, axis: str) -> None:
        try:
            self.controller.set_viewport_axis(axis)
        except ValueError as exc:
            self.status_var.set(str(exc))
