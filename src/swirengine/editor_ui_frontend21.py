from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .editor_audio_frontend21 import TkAudioEditorApp21
from .editor_ui_tooling21 import EditorUIHudTooling21, EditorUIHudToolingError
from .editor_viewport_frontend21 import EditorProductionViewportController21


@dataclass(frozen=True, slots=True)
class UIHudRow21:
    name: str
    kind: str
    text: str
    x: float
    y: float
    width: float
    height: float
    value: float
    layer: int


@dataclass(frozen=True, slots=True)
class UIHudPanelFrame21:
    path: str
    dirty: bool
    elements: tuple[UIHudRow21, ...]


class EditorUIHudPanelController21:
    """Toolkit-neutral creator adapter over runtime-backed UI/HUD authoring."""

    def __init__(self, tooling: EditorUIHudTooling21) -> None:
        if not isinstance(tooling, EditorUIHudTooling21):
            raise TypeError("tooling must be an EditorUIHudTooling21")
        self.tooling = tooling
        self._status = "UI/HUD tooling ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self) -> UIHudPanelFrame21:
        snapshot = self.tooling.snapshot()
        return UIHudPanelFrame21(
            path=snapshot.path,
            dirty=snapshot.dirty,
            elements=tuple(
                UIHudRow21(
                    item.name,
                    item.kind,
                    item.text,
                    item.x,
                    item.y,
                    item.width,
                    item.height,
                    item.value,
                    item.layer,
                )
                for item in snapshot.elements
            ),
        )

    def create_element(self, name: str, kind: str, **settings: Any) -> UIHudPanelFrame21:
        self.tooling.create_element(name, kind, **settings)
        self._status = f"Created {kind} {name}"
        return self.frame()

    def update_element(self, name: str, **changes: Any) -> UIHudPanelFrame21:
        self.tooling.update_element(name, **changes)
        self._status = f"Updated UI/HUD element {name}"
        return self.frame()

    def duplicate_element(self, name: str, new_name: str) -> UIHudPanelFrame21:
        self.tooling.duplicate_element(name, new_name)
        self._status = f"Duplicated UI/HUD element {name} as {new_name}"
        return self.frame()

    def remove_element(self, name: str) -> UIHudPanelFrame21:
        self.tooling.remove_element(name)
        self._status = f"Removed UI/HUD element {name}"
        return self.frame()

    def validate_runtime(self) -> UIHudPanelFrame21:
        manager = self.tooling.build_runtime()
        self._status = (
            f"Runtime preview valid: {len(manager.controls)} controls / "
            f"{len(manager.scene.objects)} render objects"
        )
        return self.frame()

    def save(self) -> UIHudPanelFrame21:
        snapshot = self.tooling.save()
        self._status = f"Saved UI/HUD configuration {snapshot.path}"
        return self.frame()

    def reload(self) -> UIHudPanelFrame21:
        self.tooling.load()
        self._status = "Reloaded saved UI/HUD configuration"
        return self.frame()


class TkUIHudEditorApp21(TkAudioEditorApp21):
    """Production SwirEditor shell with integrated UI/HUD creator authoring."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        ui_hud: EditorUIHudTooling21,
        **kwargs: Any,
    ) -> None:
        self.ui_hud_controller = EditorUIHudPanelController21(ui_hud)
        self._ui_hud_window: Any | None = None
        self._ui_hud_tree: Any | None = None
        self._ui_hud_status_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        hud = self.tk.Menu(menu, tearoff=False)
        hud.add_command(label="HUD Designer…", command=self._open_ui_hud_panel)
        menu.add_cascade(label="UI / HUD", menu=hud)

    def _open_ui_hud_panel(self) -> None:
        if self._ui_hud_window is not None and self._ui_hud_window.winfo_exists():
            self._ui_hud_window.deiconify()
            self._ui_hud_window.lift()
            self._ui_hud_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — UI / HUD")
        window.geometry("1120x680")
        window.minsize(820, 500)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_ui_hud_panel)
        self._ui_hud_window = window

        body = self.ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        columns = ("name", "kind", "text", "x", "y", "size", "value", "layer")
        tree = self.ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        for key, label, width in (
            ("name", "Name", 170),
            ("kind", "Kind", 90),
            ("text", "Text", 230),
            ("x", "X", 70),
            ("y", "Y", 70),
            ("size", "Size", 110),
            ("value", "Value", 80),
            ("layer", "Layer", 70),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key in {"name", "text"})
        tree.pack(fill="both", expand=True)
        self._ui_hud_tree = tree

        actions = self.ttk.Frame(window, padding=(12, 0, 12, 8))
        actions.pack(fill="x")
        for label, command in (
            ("Add…", self._ui_hud_add),
            ("Edit…", self._ui_hud_edit),
            ("Duplicate…", self._ui_hud_duplicate),
            ("Remove", self._ui_hud_remove),
            ("Validate Runtime", self._ui_hud_validate),
            ("Save", self._ui_hud_save),
            ("Reload", self._ui_hud_reload),
        ):
            self.ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6))

        footer = self.ttk.Frame(window, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        self._ui_hud_status_var = self.tk.StringVar()
        self.ttk.Label(footer, textvariable=self._ui_hud_status_var).pack(side="left")
        self.ttk.Button(footer, text="Close", command=self._close_ui_hud_panel).pack(side="right")
        self._refresh_ui_hud_panel()

    def _refresh_ui_hud_panel(self) -> None:
        frame = self.ui_hud_controller.frame()
        tree = self._ui_hud_tree
        if tree is not None:
            tree.delete(*tree.get_children())
            for index, row in enumerate(frame.elements):
                tree.insert(
                    "",
                    "end",
                    iid=f"ui-hud-{index}",
                    values=(
                        row.name,
                        row.kind,
                        row.text,
                        f"{row.x:.1f}",
                        f"{row.y:.1f}",
                        f"{row.width:.0f}×{row.height:.0f}",
                        f"{row.value:.2f}" if row.kind == "progress" else "—",
                        row.layer,
                    ),
                )
        if self._ui_hud_status_var is not None:
            dirty = " · unsaved" if frame.dirty else ""
            self._ui_hud_status_var.set(self.ui_hud_controller.status + dirty)

    def _selected_ui_hud_name(self) -> str | None:
        tree = self._ui_hud_tree
        if tree is None:
            return None
        selection = tree.selection()
        if not selection:
            return None
        values = tree.item(selection[0], "values")
        return str(values[0]) if values else None

    def _ui_hud_add(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add UI/HUD element", "Name:", parent=self._ui_hud_window)
        if not name:
            return
        kind = simpledialog.askstring(
            "Add UI/HUD element",
            "Kind (label/panel/button/progress):",
            initialvalue="label",
            parent=self._ui_hud_window,
        )
        if not kind:
            return
        text = ""
        if kind.strip().lower() in {"label", "button"}:
            text = simpledialog.askstring(
                "Add UI/HUD element",
                "Text:",
                initialvalue=name,
                parent=self._ui_hud_window,
            )
            if text is None:
                return
        self._ui_hud_action(
            lambda: self.ui_hud_controller.create_element(name, kind, text=text)
        )

    def _ui_hud_edit(self) -> None:
        from tkinter import simpledialog

        name = self._selected_ui_hud_name()
        if name is None:
            return
        frame = self.ui_hud_controller.frame()
        row = next(item for item in frame.elements if item.name == name)
        text = simpledialog.askstring(
            "Edit UI/HUD element",
            "Text:",
            initialvalue=row.text,
            parent=self._ui_hud_window,
        )
        if text is None:
            return
        x = simpledialog.askfloat(
            "Edit UI/HUD element", "X:", initialvalue=row.x, parent=self._ui_hud_window
        )
        if x is None:
            return
        y = simpledialog.askfloat(
            "Edit UI/HUD element", "Y:", initialvalue=row.y, parent=self._ui_hud_window
        )
        if y is None:
            return
        changes: dict[str, Any] = {"text": text, "x": x, "y": y}
        if row.kind == "progress":
            value = simpledialog.askfloat(
                "Edit UI/HUD element",
                "Progress value (0..1):",
                initialvalue=row.value,
                minvalue=0.0,
                maxvalue=1.0,
                parent=self._ui_hud_window,
            )
            if value is None:
                return
            changes["value"] = value
        self._ui_hud_action(lambda: self.ui_hud_controller.update_element(name, **changes))

    def _ui_hud_duplicate(self) -> None:
        from tkinter import simpledialog

        name = self._selected_ui_hud_name()
        if name is None:
            return
        new_name = simpledialog.askstring(
            "Duplicate UI/HUD element",
            "New name:",
            initialvalue=f"{name}_copy",
            parent=self._ui_hud_window,
        )
        if not new_name:
            return
        self._ui_hud_action(lambda: self.ui_hud_controller.duplicate_element(name, new_name))

    def _ui_hud_remove(self) -> None:
        name = self._selected_ui_hud_name()
        if name is None:
            return
        if not self.messagebox.askyesno(
            "Remove UI/HUD element",
            f"Remove {name}?",
            parent=self._ui_hud_window,
        ):
            return
        self._ui_hud_action(lambda: self.ui_hud_controller.remove_element(name))

    def _ui_hud_validate(self) -> None:
        self._ui_hud_action(self.ui_hud_controller.validate_runtime)

    def _ui_hud_save(self) -> None:
        self._ui_hud_action(self.ui_hud_controller.save)

    def _ui_hud_reload(self) -> None:
        self._ui_hud_action(self.ui_hud_controller.reload)

    def _ui_hud_action(self, action: Any) -> None:
        try:
            action()
        except (EditorUIHudToolingError, OSError, TypeError, ValueError) as exc:
            self.messagebox.showerror("SwirEditor — UI / HUD", str(exc), parent=self._ui_hud_window)
            return
        self._refresh_ui_hud_panel()

    def _close_ui_hud_panel(self) -> None:
        window, self._ui_hud_window = self._ui_hud_window, None
        self._ui_hud_tree = None
        self._ui_hud_status_var = None
        if window is not None and window.winfo_exists():
            window.destroy()
