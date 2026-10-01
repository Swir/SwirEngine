from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .editor_lighting_frontend22 import TkLightingEditorApp22
from .editor_ui_designer22 import EditorUIDesignerPanelController22
from .ui_designer22 import (
    EditorUIDesignerTooling22,
    UIAnimationKeyframeSpec22,
    UIAnimationSpec22,
    UIAnimationTrackSpec22,
    UIStyleSpec22,
    UIWidgetSpec22,
)


class TkUIDesignerEditorApp22(TkLightingEditorApp22):
    """Integrated UI Designer 2.0 with isolated runtime-backed preview."""

    def __init__(
        self,
        controller: Any,
        *,
        ui_designer: EditorUIDesignerTooling22,
        **kwargs: Any,
    ) -> None:
        self.ui_designer_controller = EditorUIDesignerPanelController22(ui_designer)
        self._ui_designer_window: Any | None = None
        self._ui_designer_after: Any | None = None
        self._ui_designer_notebook: Any | None = None
        self._ui_designer_widget_tree: Any | None = None
        self._ui_designer_style_list: Any | None = None
        self._ui_designer_animation_list: Any | None = None
        self._ui_designer_image: Any | None = None
        self._ui_designer_photo: Any | None = None
        self._ui_designer_status: Any | None = None
        self._ui_designer_diagnostics: Any | None = None
        self._ui_designer_seek_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        menu.add_command(label="UI Designer 2.0...", command=self._open_ui_designer)

    def _open_ui_designer(self) -> None:
        if (
            self._ui_designer_window is not None
            and self._ui_designer_window.winfo_exists()
        ):
            self._ui_designer_window.deiconify()
            self._ui_designer_window.lift()
            return
        window = self.tk.Toplevel(self.root)
        self._ui_designer_window = window
        window.title("SwirEditor 2.2 - UI Designer 2.0")
        window.geometry("1220x760")
        window.minsize(1040, 640)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_ui_designer)
        window.columnconfigure(0, weight=1)
        window.columnconfigure(1, weight=1)
        window.rowconfigure(0, weight=1)

        authoring = self.ttk.Frame(window, padding=10)
        authoring.grid(row=0, column=0, sticky="nsew")
        authoring.columnconfigure(0, weight=1)
        authoring.rowconfigure(1, weight=1)
        toolbar = self.ttk.Frame(authoring)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.ttk.Button(toolbar, text="Save", command=self._ui_designer_save).pack(
            side="left"
        )
        self.ttk.Button(toolbar, text="Reload", command=self._ui_designer_reload).pack(
            side="left", padx=(6, 0)
        )
        notebook = self.ttk.Notebook(authoring)
        self._ui_designer_notebook = notebook
        notebook.grid(row=1, column=0, sticky="nsew")
        self._build_ui_designer_widgets_tab(notebook)
        self._build_ui_designer_styles_tab(notebook)
        self._build_ui_designer_animations_tab(notebook)

        preview = self.ttk.LabelFrame(window, text="Isolated Runtime Preview", padding=10)
        preview.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(2, weight=1)
        controls = self.ttk.Frame(preview)
        controls.grid(row=0, column=0, sticky="ew")
        for label, command in (
            ("Start", self._ui_designer_start),
            ("Pause", self._ui_designer_pause),
            ("Resume", self._ui_designer_resume),
            ("Step", self._ui_designer_step),
            ("Stop", self._ui_designer_stop),
        ):
            self.ttk.Button(controls, text=label, command=command).pack(
                side="left", padx=(0, 4)
            )
        self._ui_designer_seek_var = self.tk.StringVar(value="0.0")
        self.ttk.Entry(
            controls, textvariable=self._ui_designer_seek_var, width=8
        ).pack(side="left", padx=(8, 4))
        self.ttk.Button(controls, text="Seek", command=self._ui_designer_seek).pack(
            side="left"
        )
        self.ttk.Label(
            preview,
            text=(
                "Fixed 10 Hz editor preview. Project actions are inert; keyboard and "
                "gamepad focus rules remain owned by the shipping UI runtime."
            ),
            wraplength=500,
        ).grid(row=1, column=0, sticky="w", pady=8)
        self._ui_designer_image = self.ttk.Label(
            preview, anchor="center", text="Start preview to render"
        )
        self._ui_designer_image.grid(row=2, column=0, sticky="nsew")
        self._ui_designer_diagnostics = self.tk.Text(
            preview, height=8, wrap="word", state="disabled"
        )
        self._ui_designer_diagnostics.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self._ui_designer_status = self.tk.StringVar(
            value=self.ui_designer_controller.status
        )
        self.ttk.Label(
            window,
            textvariable=self._ui_designer_status,
            padding=10,
            wraplength=1100,
        ).grid(row=1, column=0, columnspan=2, sticky="ew")
        self._refresh_ui_designer()
        self._schedule_ui_designer()

    def _build_ui_designer_widgets_tab(self, notebook: Any) -> None:
        tab = self.ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Widgets")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        tree = self.ttk.Treeview(
            tab,
            columns=("id", "kind", "parent", "style"),
            show="headings",
            selectmode="browse",
        )
        for key, label, width in (
            ("id", "Id", 140),
            ("kind", "Kind", 80),
            ("parent", "Parent", 120),
            ("style", "Style", 100),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        self._ui_designer_widget_tree = tree
        actions = self.ttk.Frame(tab)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for label, command in (
            ("Add", self._ui_designer_add_widget),
            ("Edit", self._ui_designer_edit_widget),
            ("Remove", self._ui_designer_remove_widget),
        ):
            self.ttk.Button(actions, text=label, command=command).pack(
                side="left", padx=(0, 6)
            )

    def _build_ui_designer_styles_tab(self, notebook: Any) -> None:
        tab = self.ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Reusable Styles")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._ui_designer_style_list = self.tk.Listbox(
            tab, exportselection=False, height=18
        )
        self._ui_designer_style_list.grid(row=0, column=0, sticky="nsew")
        actions = self.ttk.Frame(tab)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.ttk.Button(
            actions, text="Add", command=self._ui_designer_add_style
        ).pack(side="left", padx=(0, 6))
        self.ttk.Button(
            actions, text="Edit States", command=self._ui_designer_edit_style
        ).pack(side="left", padx=(0, 6))
        self.ttk.Button(
            actions, text="Remove", command=self._ui_designer_remove_style
        ).pack(side="left")

    def _build_ui_designer_animations_tab(self, notebook: Any) -> None:
        tab = self.ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Animations")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._ui_designer_animation_list = self.tk.Listbox(
            tab, exportselection=False, height=18
        )
        self._ui_designer_animation_list.grid(row=0, column=0, sticky="nsew")
        actions = self.ttk.Frame(tab)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.ttk.Button(
            actions, text="Add Track Animation", command=self._ui_designer_add_animation
        ).pack(side="left", padx=(0, 6))
        self.ttk.Button(
            actions, text="Remove", command=self._ui_designer_remove_animation
        ).pack(side="left")

    def _selected_ui_designer_widget(self) -> str | None:
        tree = self._ui_designer_widget_tree
        if tree is None:
            return None
        selection = tree.selection()
        if not selection:
            return None
        values = tree.item(selection[0], "values")
        return str(values[0]) if values else None

    @staticmethod
    def _selected_list_value(widget: Any) -> str | None:
        if widget is None:
            return None
        selection = widget.curselection()
        return str(widget.get(selection[0])) if selection else None

    def _ui_designer_add_widget(self) -> None:
        from tkinter import simpledialog

        widget_id = simpledialog.askstring(
            "Add UI widget", "Widget id:", parent=self._ui_designer_window
        )
        if not widget_id:
            return
        kind = simpledialog.askstring(
            "Add UI widget",
            "Kind (stack/panel/label/button/progress):",
            initialvalue="button",
            parent=self._ui_designer_window,
        )
        if not kind:
            return
        text = simpledialog.askstring(
            "Add UI widget",
            "Text:",
            initialvalue=widget_id,
            parent=self._ui_designer_window,
        )
        if text is None:
            return
        self._ui_designer_action(
            lambda: self.ui_designer_controller.upsert_widget(
                UIWidgetSpec22(widget_id, kind.strip().lower(), text=text)
            )
        )

    def _ui_designer_edit_widget(self) -> None:
        from tkinter import simpledialog

        widget_id = self._selected_ui_designer_widget()
        if widget_id is None:
            return
        asset = self.ui_designer_controller.tooling.snapshot().asset
        widget = next(item for item in asset.widgets if item.id == widget_id)
        text = simpledialog.askstring(
            "Edit UI widget",
            "Text:",
            initialvalue=widget.text,
            parent=self._ui_designer_window,
        )
        if text is None:
            return
        parent = simpledialog.askstring(
            "Edit UI widget",
            "Parent id (blank for root):",
            initialvalue=widget.parent or "",
            parent=self._ui_designer_window,
        )
        if parent is None:
            return
        style = simpledialog.askstring(
            "Edit UI widget",
            "Reusable style (blank for theme):",
            initialvalue=widget.style or "",
            parent=self._ui_designer_window,
        )
        if style is None:
            return
        width = simpledialog.askfloat(
            "Edit UI widget",
            "Width:",
            initialvalue=widget.width,
            minvalue=0.001,
            parent=self._ui_designer_window,
        )
        if width is None:
            return
        height = simpledialog.askfloat(
            "Edit UI widget",
            "Height:",
            initialvalue=widget.height,
            minvalue=0.001,
            parent=self._ui_designer_window,
        )
        if height is None:
            return
        opacity = simpledialog.askfloat(
            "Edit UI widget",
            "Opacity (0..1):",
            initialvalue=widget.opacity,
            minvalue=0.0,
            maxvalue=1.0,
            parent=self._ui_designer_window,
        )
        if opacity is None:
            return
        anchor = simpledialog.askstring(
            "Edit UI widget",
            (
                "Anchor (blank or center/top_left/top/top_right/left/right/"
                "bottom_left/bottom/bottom_right):"
            ),
            initialvalue=widget.anchor or "",
            parent=self._ui_designer_window,
        )
        if anchor is None:
            return
        axis = simpledialog.askstring(
            "Edit UI widget",
            "Container axis (horizontal/vertical):",
            initialvalue=widget.axis,
            parent=self._ui_designer_window,
        )
        if axis is None:
            return
        enabled = simpledialog.askstring(
            "Edit UI widget",
            "Enabled (true/false):",
            initialvalue="true" if widget.enabled else "false",
            parent=self._ui_designer_window,
        )
        if enabled is None:
            return
        focusable = simpledialog.askstring(
            "Edit UI widget",
            "Focusable (auto/true/false):",
            initialvalue=(
                "auto"
                if widget.focusable is None
                else "true" if widget.focusable else "false"
            ),
            parent=self._ui_designer_window,
        )
        if focusable is None:
            return
        action = simpledialog.askstring(
            "Edit UI widget",
            "Action label (blank for none):",
            initialvalue=widget.action or "",
            parent=self._ui_designer_window,
        )
        if action is None:
            return
        self._ui_designer_action(
            lambda: self.ui_designer_controller.set_widget_fields(
                widget.id,
                text=text,
                parent=parent.strip() or None,
                style=style.strip() or None,
                width=width,
                height=height,
                opacity=opacity,
                anchor=anchor.strip().lower() or None,
                axis=axis.strip().lower(),
                enabled=self._ui_designer_bool(enabled, "enabled"),
                focusable=self._ui_designer_optional_bool(focusable),
                action=action.strip() or None,
            )
        )

    def _ui_designer_remove_widget(self) -> None:
        widget_id = self._selected_ui_designer_widget()
        if widget_id is None:
            return
        if not self.messagebox.askyesno(
            "Remove UI widget",
            f"Remove {widget_id}?",
            parent=self._ui_designer_window,
        ):
            return
        self._ui_designer_action(
            lambda: self.ui_designer_controller.remove_widget(widget_id)
        )

    def _ui_designer_add_style(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Add reusable UI style", "Style name:", parent=self._ui_designer_window
        )
        if not name:
            return
        self._ui_designer_action(
            lambda: self.ui_designer_controller.upsert_style(UIStyleSpec22(name))
        )

    def _ui_designer_remove_style(self) -> None:
        name = self._selected_list_value(self._ui_designer_style_list)
        if name is not None:
            self._ui_designer_action(
                lambda: self.ui_designer_controller.remove_style(name)
            )

    def _ui_designer_edit_style(self) -> None:
        from tkinter import simpledialog

        name = self._selected_list_value(self._ui_designer_style_list)
        if name is None:
            return
        asset = self.ui_designer_controller.tooling.snapshot().asset
        style = next(item for item in asset.styles if item.name == name)
        changes: dict[str, tuple[float, float, float, float] | None] = {}
        for field in ("button", "button_hover", "button_pressed", "button_focused"):
            current = getattr(style, field)
            initial = "" if current is None else ", ".join(str(item) for item in current)
            raw = simpledialog.askstring(
                "Edit reusable UI style",
                f"{field.replace('_', ' ')} RGBA (blank inherits theme):",
                initialvalue=initial,
                parent=self._ui_designer_window,
            )
            if raw is None:
                return
            changes[field] = self._ui_designer_optional_rgba(raw, field)
        self._ui_designer_action(
            lambda: self.ui_designer_controller.set_style_fields(name, **changes)
        )

    def _ui_designer_add_animation(self) -> None:
        from tkinter import simpledialog

        widget_id = self._selected_ui_designer_widget()
        if widget_id is None:
            widget_id = simpledialog.askstring(
                "Add UI animation",
                "Target widget id:",
                parent=self._ui_designer_window,
            )
        if not widget_id:
            return
        name = simpledialog.askstring(
            "Add UI animation", "Animation name:", parent=self._ui_designer_window
        )
        if not name:
            return
        duration = simpledialog.askfloat(
            "Add UI animation",
            "Duration in seconds:",
            initialvalue=0.5,
            minvalue=0.001,
            parent=self._ui_designer_window,
        )
        if duration is None:
            return
        animation = UIAnimationSpec22(
            name,
            duration,
            (
                UIAnimationTrackSpec22(
                    widget_id,
                    "opacity",
                    (
                        UIAnimationKeyframeSpec22(0.0, 1.0),
                        UIAnimationKeyframeSpec22(duration, 0.25),
                    ),
                ),
            ),
        )
        self._ui_designer_action(
            lambda: self.ui_designer_controller.upsert_animation(animation)
        )

    def _ui_designer_remove_animation(self) -> None:
        name = self._selected_list_value(self._ui_designer_animation_list)
        if name is not None:
            self._ui_designer_action(
                lambda: self.ui_designer_controller.remove_animation(name)
            )

    def _ui_designer_start(self) -> None:
        animation = self._selected_list_value(self._ui_designer_animation_list)
        self._ui_designer_action(lambda: self.ui_designer_controller.start(animation))

    def _ui_designer_pause(self) -> None:
        self._ui_designer_action(self.ui_designer_controller.pause)

    def _ui_designer_resume(self) -> None:
        self._ui_designer_action(self.ui_designer_controller.resume)

    def _ui_designer_step(self) -> None:
        def step() -> None:
            self.ui_designer_controller.step()
            self._capture_ui_designer()

        self._ui_designer_action(step)

    def _ui_designer_seek(self) -> None:
        self._ui_designer_action(
            lambda: self.ui_designer_controller.seek(
                float(self._ui_designer_value(self._ui_designer_seek_var))
            )
        )

    def _ui_designer_stop(self) -> None:
        self._ui_designer_action(self.ui_designer_controller.stop)
        self._clear_ui_designer_image()

    def _ui_designer_save(self) -> None:
        self._ui_designer_action(self.ui_designer_controller.save)

    def _ui_designer_reload(self) -> None:
        self._ui_designer_action(self.ui_designer_controller.reload)

    def _ui_designer_action(self, action: Any) -> None:
        try:
            action()
            self._refresh_ui_designer()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._ui_designer_error(exc)

    def _capture_ui_designer(self) -> None:
        image = self.ui_designer_controller.capture(480, 320)
        if image is None:
            return
        self._ui_designer_photo = self.tk.PhotoImage(
            master=self.root, data=image.to_ppm(), format="PPM"
        )
        self._ui_designer_image.configure(image=self._ui_designer_photo, text="")

    def _schedule_ui_designer(self) -> None:
        if self._ui_designer_after is None and self._ui_designer_window is not None:
            self._ui_designer_after = self.root.after(100, self._ui_designer_tick)

    def _ui_designer_tick(self) -> None:
        self._ui_designer_after = None
        if self._ui_designer_window is None:
            return
        try:
            if self.ui_designer_controller.active:
                image = self.ui_designer_controller.update_preview(0.1, 480, 320)
                if image is not None:
                    self._ui_designer_photo = self.tk.PhotoImage(
                        master=self.root, data=image.to_ppm(), format="PPM"
                    )
                    self._ui_designer_image.configure(
                        image=self._ui_designer_photo, text=""
                    )
            self._refresh_ui_designer()
        except Exception as exc:  # noqa: BLE001 - preserve the desktop event loop
            self._clear_ui_designer_image()
            self._ui_designer_error(exc)
        self._schedule_ui_designer()

    def _refresh_ui_designer(self) -> None:
        frame = self.ui_designer_controller.frame()
        selected_widget = self._selected_ui_designer_widget()
        tree = self._ui_designer_widget_tree
        if tree is not None:
            tree.delete(*tree.get_children())
            selected_item = None
            for widget in frame.asset.widgets:
                item = tree.insert(
                    "",
                    "end",
                    values=(
                        widget.id,
                        widget.kind,
                        widget.parent or "",
                        widget.style or "",
                    ),
                )
                if widget.id == selected_widget:
                    selected_item = item
            if selected_item is not None:
                tree.selection_set(selected_item)
                tree.focus(selected_item)
        self._refresh_ui_designer_list(
            self._ui_designer_style_list,
            tuple(style.name for style in frame.asset.styles),
        )
        self._refresh_ui_designer_list(
            self._ui_designer_animation_list,
            tuple(animation.name for animation in frame.asset.animations),
        )
        diagnostics = "Preview is stopped"
        if frame.diagnostics is not None:
            payload = (
                asdict(frame.diagnostics)
                if is_dataclass(frame.diagnostics)
                else {"diagnostics": frame.diagnostics}
            )
            diagnostics = "\n".join(
                f"{key}: {value}" for key, value in payload.items()
            )
        self._write_ui_designer_diagnostics(diagnostics)
        if self._ui_designer_seek_var is not None:
            self._ui_designer_seek_var.set(f"{frame.preview_time:.3f}")
        if self._ui_designer_status is not None:
            self._ui_designer_status.set(frame.status)

    @staticmethod
    def _refresh_ui_designer_list(widget: Any, values: tuple[str, ...]) -> None:
        if widget is None:
            return
        selected = TkUIDesignerEditorApp22._selected_list_value(widget)
        widget.delete(0, "end")
        for value in values:
            widget.insert("end", value)
        if selected in values:
            widget.selection_set(values.index(selected))

    def _write_ui_designer_diagnostics(self, text: str) -> None:
        widget = self._ui_designer_diagnostics
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _ui_designer_error(self, exc: Exception) -> None:
        if self._ui_designer_status is not None:
            self._ui_designer_status.set(str(exc))
        self.controller.console.write(str(exc), level="error", source="ui-designer")

    def _clear_ui_designer_image(self) -> None:
        self._ui_designer_photo = None
        if self._ui_designer_image is not None:
            self._ui_designer_image.configure(
                image="", text="Preview stopped; authored asset unchanged"
            )

    def _close_ui_designer(self) -> None:
        if self._ui_designer_after is not None:
            try:
                self.root.after_cancel(self._ui_designer_after)
            except (RuntimeError, TypeError, ValueError):
                pass
            self._ui_designer_after = None
        failure: Exception | None = None
        try:
            self.ui_designer_controller.stop()
        except Exception as exc:  # noqa: BLE001 - window resources still need release
            failure = exc
        if self._ui_designer_window is not None:
            self._ui_designer_window.destroy()
            self._ui_designer_window = None
        self._ui_designer_photo = None
        self._ui_designer_image = None
        if failure is not None:
            self._ui_designer_error(failure)

    def close(self) -> None:
        self._close_ui_designer()
        super().close()

    @staticmethod
    def _ui_designer_value(variable: Any) -> str:
        if variable is None:
            raise RuntimeError("UI Designer is not open")
        return str(variable.get()).strip()

    @staticmethod
    def _ui_designer_bool(value: str, label: str) -> bool:
        normalized = str(value).strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise ValueError(f"{label} must be true or false")

    @classmethod
    def _ui_designer_optional_bool(cls, value: str) -> bool | None:
        normalized = str(value).strip().lower()
        if normalized in {"", "auto"}:
            return None
        return cls._ui_designer_bool(normalized, "focusable")

    @staticmethod
    def _ui_designer_optional_rgba(
        value: str, label: str
    ) -> tuple[float, float, float, float] | None:
        normalized = str(value).strip()
        if not normalized:
            return None
        parts = tuple(float(item.strip()) for item in normalized.split(","))
        if len(parts) != 4 or any(item < 0.0 or item > 1.0 for item in parts):
            raise ValueError(f"{label} must contain four RGBA values in 0..1")
        return parts
