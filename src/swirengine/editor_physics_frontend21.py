from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .editor_animation_frontend21 import TkAnimationEditorApp21
from .editor_physics_tooling21 import (
    EditorPhysicsTooling21,
    EditorPhysicsToolingError,
    RuntimePhysicsBody21,
)
from .editor_viewport_frontend21 import EditorProductionViewportController21


@dataclass(frozen=True, slots=True)
class PhysicsBodyRow21:
    name: str
    dimension: str
    shape: str
    body_type: str
    size: tuple[float, ...]
    enabled: bool
    layer: int
    mask: int
    tag: str


@dataclass(frozen=True, slots=True)
class PhysicsPanelFrame21:
    path: str
    dirty: bool
    bodies: tuple[PhysicsBodyRow21, ...]
    selected_name: str | None
    preview_name: str | None
    preview_type: str | None
    preview_collider: str | None


class EditorPhysicsPanelController21:
    """Toolkit-neutral creator adapter over runtime-backed physics authoring."""

    def __init__(self, tooling: EditorPhysicsTooling21) -> None:
        if not isinstance(tooling, EditorPhysicsTooling21):
            raise TypeError("tooling must be an EditorPhysicsTooling21")
        self.tooling = tooling
        self._preview_name: str | None = None
        self._preview_type: str | None = None
        self._preview_collider: str | None = None
        self._status = "Physics tooling ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self, selected_name: str | None = None) -> PhysicsPanelFrame21:
        snapshot = self.tooling.snapshot()
        rows = tuple(
            PhysicsBodyRow21(
                name=body.name,
                dimension=body.dimension,
                shape=body.shape,
                body_type=body.body_type,
                size=body.size,
                enabled=body.enabled,
                layer=body.layer,
                mask=body.mask,
                tag=body.tag,
            )
            for body in snapshot.bodies
        )
        names = {row.name for row in rows}
        if selected_name not in names:
            selected_name = rows[0].name if rows else None
        return PhysicsPanelFrame21(
            path=snapshot.path,
            dirty=snapshot.dirty,
            bodies=rows,
            selected_name=selected_name,
            preview_name=self._preview_name,
            preview_type=self._preview_type,
            preview_collider=self._preview_collider,
        )

    def create_body(
        self,
        name: str,
        *,
        dimension: str,
        shape: str = "box",
        body_type: str = "dynamic",
        size: tuple[float, ...] | None = None,
        **changes: Any,
    ) -> PhysicsPanelFrame21:
        self.tooling.create_body(
            name,
            dimension=dimension,
            shape=shape,
            body_type=body_type,
            size=size,
            **changes,
        )
        self._clear_preview()
        self._status = f"Created physics body {name}"
        return self.frame(name)

    def update_body(self, name: str, **changes: Any) -> PhysicsPanelFrame21:
        self.tooling.update_body(name, **changes)
        self._clear_preview()
        self._status = f"Updated physics body {name}"
        return self.frame(name)

    def rename_body(self, name: str, new_name: str) -> PhysicsPanelFrame21:
        self.tooling.rename_body(name, new_name)
        self._clear_preview()
        self._status = f"Renamed physics body {name} to {new_name}"
        return self.frame(new_name)

    def remove_body(self, name: str) -> PhysicsPanelFrame21:
        self.tooling.remove_body(name)
        self._clear_preview()
        self._status = f"Removed physics body {name}"
        return self.frame()

    def preview(
        self,
        name: str,
        *,
        position: tuple[float, ...] | None = None,
    ) -> tuple[PhysicsPanelFrame21, RuntimePhysicsBody21]:
        runtime = self.tooling.build_runtime(name, position=position)
        self._preview_name = name
        self._preview_type = type(runtime).__name__
        collider = getattr(runtime, "collider", None)
        self._preview_collider = None if collider is None else type(collider).__name__
        self._status = f"Built runtime physics preview for {name}"
        return self.frame(name), runtime

    def save(self) -> PhysicsPanelFrame21:
        snapshot = self.tooling.save()
        self._status = f"Saved physics configuration {snapshot.path}"
        return self.frame()

    def reload(self) -> PhysicsPanelFrame21:
        self.tooling.load()
        self._clear_preview()
        self._status = "Reloaded saved physics configuration"
        return self.frame()

    def _clear_preview(self) -> None:
        self._preview_name = None
        self._preview_type = None
        self._preview_collider = None


def parse_physics_size21(text: str) -> tuple[float, ...]:
    """Parse comma-separated collider dimensions from the desktop panel."""

    parts = tuple(part.strip() for part in str(text).split(",") if part.strip())
    if not parts:
        raise ValueError("size must contain at least one number")
    try:
        return tuple(float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("size must be comma-separated numbers") from exc


class TkPhysicsEditorApp21(TkAnimationEditorApp21):
    """Production SwirEditor shell with integrated physics/collision authoring."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        physics: EditorPhysicsTooling21,
        **kwargs: Any,
    ) -> None:
        self.physics_controller = EditorPhysicsPanelController21(physics)
        self._physics_window: Any | None = None
        self._physics_tree: Any | None = None
        self._physics_status_var: Any | None = None
        self._physics_preview_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        physics = self.tk.Menu(menu, tearoff=False)
        physics.add_command(
            label="Collision & Bodies…",
            command=self._open_physics_panel,
        )
        menu.add_cascade(label="Physics", menu=physics)

    def _open_physics_panel(self) -> None:
        if self._physics_window is not None and self._physics_window.winfo_exists():
            self._physics_window.deiconify()
            self._physics_window.lift()
            self._physics_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — Physics & Collision")
        window.geometry("980x600")
        window.minsize(800, 480)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_physics_panel)
        self._physics_window = window

        body_frame = self.ttk.LabelFrame(window, text="Project physics bodies", padding=8)
        body_frame.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        tree = self.ttk.Treeview(
            body_frame,
            columns=("name", "dimension", "shape", "type", "size", "layer", "mask", "enabled"),
            show="headings",
            selectmode="browse",
        )
        columns = (
            ("name", "Name", 180),
            ("dimension", "Dim", 55),
            ("shape", "Shape", 80),
            ("type", "Body type", 90),
            ("size", "Size", 150),
            ("layer", "Layer", 65),
            ("mask", "Mask", 90),
            ("enabled", "Enabled", 70),
        )
        for column, title, width in columns:
            tree.heading(column, text=title)
            tree.column(column, width=width, stretch=column in {"name", "size"})
        tree.pack(fill="both", expand=True)
        self._physics_tree = tree

        actions = self.ttk.Frame(body_frame)
        actions.pack(fill="x", pady=(8, 0))
        for label, command in (
            ("Add…", self._physics_add),
            ("Edit…", self._physics_edit),
            ("Rename…", self._physics_rename),
            ("Remove", self._physics_remove),
            ("Runtime Preview", self._physics_preview),
            ("Save", self._physics_save),
            ("Reload", self._physics_reload),
        ):
            self.ttk.Button(actions, text=label, command=command).pack(
                side="left",
                padx=(0, 6),
            )

        preview = self.ttk.LabelFrame(window, text="Runtime-backed preview", padding=8)
        preview.pack(fill="x", padx=12, pady=(0, 8))
        self._physics_preview_var = self.tk.StringVar(value="No runtime preview")
        self.ttk.Label(preview, textvariable=self._physics_preview_var).pack(
            side="left",
            fill="x",
            expand=True,
        )

        footer = self.ttk.Frame(window, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        self._physics_status_var = self.tk.StringVar()
        self.ttk.Label(footer, textvariable=self._physics_status_var).pack(side="left")
        self.ttk.Button(
            footer,
            text="Close",
            command=self._close_physics_panel,
        ).pack(side="right")
        self._refresh_physics_panel()

    def _selected_physics_name(self) -> str | None:
        tree = self._physics_tree
        if tree is None:
            return None
        selected = tree.selection()
        if not selected:
            return None
        values = tree.item(selected[0], "values")
        return str(values[0]) if values else None

    def _refresh_physics_panel(self, selected_name: str | None = None) -> None:
        frame = self.physics_controller.frame(selected_name or self._selected_physics_name())
        tree = self._physics_tree
        if tree is not None:
            tree.delete(*tree.get_children())
            for index, row in enumerate(frame.bodies):
                iid = f"physics-body-{index}"
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        row.name,
                        row.dimension,
                        row.shape,
                        row.body_type,
                        " × ".join(f"{value:g}" for value in row.size),
                        row.layer,
                        row.mask,
                        "yes" if row.enabled else "no",
                    ),
                )
                if row.name == frame.selected_name:
                    tree.selection_set(iid)
        if self._physics_preview_var is not None:
            if frame.preview_name is None:
                self._physics_preview_var.set("No runtime preview")
            else:
                self._physics_preview_var.set(
                    f"{frame.preview_name}: {frame.preview_type} + {frame.preview_collider}"
                )
        if self._physics_status_var is not None:
            dirty = " · unsaved" if frame.dirty else ""
            self._physics_status_var.set(self.physics_controller.status + dirty)

    def _physics_add(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add physics body", "Name:", parent=self._physics_window)
        if not name:
            return
        dimension = simpledialog.askstring(
            "Add physics body",
            "Dimension (2d or 3d):",
            initialvalue="2d",
            parent=self._physics_window,
        )
        if not dimension:
            return
        dimension = dimension.strip().lower()
        shape = simpledialog.askstring(
            "Add physics body",
            "Shape (box or sphere; 2d supports box):",
            initialvalue="box",
            parent=self._physics_window,
        )
        if not shape:
            return
        body_type = simpledialog.askstring(
            "Add physics body",
            "Body type (dynamic, kinematic or static):",
            initialvalue="dynamic",
            parent=self._physics_window,
        )
        if not body_type:
            return
        default_size = "1, 1" if dimension == "2d" else "1, 1, 1"
        if shape.strip().lower() == "sphere":
            default_size = "0.5"
        size_text = simpledialog.askstring(
            "Add physics body",
            "Collider size (comma-separated):",
            initialvalue=default_size,
            parent=self._physics_window,
        )
        if not size_text:
            return
        self._physics_action(
            lambda: self.physics_controller.create_body(
                name,
                dimension=dimension,
                shape=shape.strip().lower(),
                body_type=body_type.strip().lower(),
                size=parse_physics_size21(size_text),
            ),
            selected_name=name,
        )

    def _physics_edit(self) -> None:
        from tkinter import simpledialog

        name = self._selected_physics_name()
        if name is None:
            return
        restitution = simpledialog.askfloat(
            "Edit physics body",
            "Restitution (0..1):",
            initialvalue=0.0,
            minvalue=0.0,
            maxvalue=1.0,
            parent=self._physics_window,
        )
        if restitution is None:
            return
        friction = simpledialog.askfloat(
            "Edit physics body",
            "Friction (>= 0):",
            initialvalue=0.5,
            minvalue=0.0,
            parent=self._physics_window,
        )
        if friction is None:
            return
        self._physics_action(
            lambda: self.physics_controller.update_body(
                name,
                restitution=restitution,
                friction=friction,
            ),
            selected_name=name,
        )

    def _physics_rename(self) -> None:
        from tkinter import simpledialog

        name = self._selected_physics_name()
        if name is None:
            return
        new_name = simpledialog.askstring(
            "Rename physics body",
            "New name:",
            initialvalue=name,
            parent=self._physics_window,
        )
        if not new_name or new_name == name:
            return
        self._physics_action(
            lambda: self.physics_controller.rename_body(name, new_name),
            selected_name=new_name,
        )

    def _physics_remove(self) -> None:
        name = self._selected_physics_name()
        if name is None:
            return
        if not self.messagebox.askyesno(
            "Remove physics body",
            f"Remove {name}?",
            parent=self._physics_window,
        ):
            return
        self._physics_action(lambda: self.physics_controller.remove_body(name))

    def _physics_preview(self) -> None:
        name = self._selected_physics_name()
        if name is None:
            return

        def action() -> PhysicsPanelFrame21:
            frame, _runtime = self.physics_controller.preview(name)
            return frame

        self._physics_action(action, selected_name=name)

    def _physics_save(self) -> None:
        self._physics_action(self.physics_controller.save)

    def _physics_reload(self) -> None:
        self._physics_action(self.physics_controller.reload)

    def _physics_action(
        self,
        action: Any,
        *,
        selected_name: str | None = None,
    ) -> None:
        try:
            action()
        except (EditorPhysicsToolingError, TypeError, ValueError) as exc:
            self.messagebox.showerror(
                "SwirEditor — Physics",
                str(exc),
                parent=self._physics_window,
            )
            return
        self._refresh_physics_panel(selected_name)

    def _close_physics_panel(self) -> None:
        window, self._physics_window = self._physics_window, None
        self._physics_tree = None
        self._physics_status_var = None
        self._physics_preview_var = None
        if window is not None and window.winfo_exists():
            window.destroy()
