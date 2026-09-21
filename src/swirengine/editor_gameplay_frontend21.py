from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .editor_console_navigation21 import TkConsoleNavigationEditorApp21
from .editor_gameplay_tooling21 import EditorGameplayTooling21
from .editor_viewport_frontend21 import EditorProductionViewportController21
from .input import InputBinding
from .shipping19 import GameSettings


@dataclass(frozen=True, slots=True)
class GameplayBindingRow21:
    action: str
    index: int
    binding: InputBinding
    display: str


@dataclass(frozen=True, slots=True)
class GameplayPanelFrame21:
    actions: tuple[str, ...]
    selected_action: str | None
    bindings: tuple[GameplayBindingRow21, ...]
    conflicts: tuple[str, ...]
    settings: GameSettings
    dirty: bool


class EditorGameplayPanelController21:
    """Toolkit-neutral adapter for SwirEditor gameplay input/settings authoring."""

    def __init__(self, tooling: EditorGameplayTooling21) -> None:
        if not isinstance(tooling, EditorGameplayTooling21):
            raise TypeError("tooling must be an EditorGameplayTooling21")
        self.tooling = tooling
        self._status = "Gameplay tooling ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self, selected_action: str | None = None) -> GameplayPanelFrame21:
        snapshot = self.tooling.snapshot()
        actions = snapshot.actions.actions()
        if selected_action not in actions:
            selected_action = actions[0] if actions else None
        bindings = ()
        if selected_action is not None:
            bindings = tuple(
                GameplayBindingRow21(
                    action=selected_action,
                    index=index,
                    binding=binding,
                    display=_binding_display(binding),
                )
                for index, binding in enumerate(snapshot.actions.bindings(selected_action))
            )
        conflicts = tuple(
            f"{item.control}: {', '.join(item.actions)}" for item in snapshot.conflicts
        )
        return GameplayPanelFrame21(
            actions=actions,
            selected_action=selected_action,
            bindings=bindings,
            conflicts=conflicts,
            settings=snapshot.settings,
            dirty=snapshot.dirty,
        )

    def add_key(self, action: str, key: str) -> GameplayPanelFrame21:
        self.tooling.add_binding(action, InputBinding("key", key))
        self._status = f"Added key binding to {action}"
        return self.frame(action)

    def add_mouse_button(self, action: str, button: int) -> GameplayPanelFrame21:
        self.tooling.add_binding(action, InputBinding("mouse_button", button))
        self._status = f"Added mouse binding to {action}"
        return self.frame(action)

    def add_gamepad_button(
        self,
        action: str,
        button: str,
        *,
        gamepad_id: int = 0,
    ) -> GameplayPanelFrame21:
        self.tooling.add_binding(
            action,
            InputBinding("gamepad_button", button, gamepad_id=gamepad_id),
        )
        self._status = f"Added gamepad button binding to {action}"
        return self.frame(action)

    def add_gamepad_axis(
        self,
        action: str,
        axis: str,
        *,
        direction: int = 0,
        threshold: float = 0.5,
        scale: float = 1.0,
        gamepad_id: int = 0,
    ) -> GameplayPanelFrame21:
        self.tooling.add_binding(
            action,
            InputBinding(
                "gamepad_axis",
                axis,
                gamepad_id=gamepad_id,
                direction=direction,
                threshold=threshold,
                scale=scale,
            ),
        )
        self._status = f"Added gamepad axis binding to {action}"
        return self.frame(action)

    def remove_binding(self, action: str, index: int) -> GameplayPanelFrame21:
        self.tooling.remove_binding(action, index)
        self._status = f"Removed binding from {action}"
        return self.frame(action)

    def reset_action(self, action: str) -> GameplayPanelFrame21:
        self.tooling.reset_action(action)
        self._status = f"Restored default bindings for {action}"
        return self.frame(action)

    def update_display(self, **changes: Any) -> GameplayPanelFrame21:
        self.tooling.update_display(**changes)
        self._status = "Updated project display defaults"
        return self.frame()

    def update_accessibility(self, **changes: Any) -> GameplayPanelFrame21:
        self.tooling.update_accessibility(**changes)
        self._status = "Updated project accessibility defaults"
        return self.frame()

    def reset_settings(self) -> GameplayPanelFrame21:
        self.tooling.reset_settings()
        self._status = "Restored default game settings"
        return self.frame()

    def reload(self) -> GameplayPanelFrame21:
        self.tooling.reload()
        self._status = "Reloaded saved gameplay configuration"
        return self.frame()


def _binding_display(binding: InputBinding) -> str:
    base = f"{binding.kind}: {binding.control}"
    if binding.kind == "gamepad_button":
        return f"{base} (pad {binding.gamepad_id})"
    if binding.kind == "gamepad_axis":
        return (
            f"{base} (pad {binding.gamepad_id}, dir {binding.direction}, "
            f"threshold {binding.threshold:g}, scale {binding.scale:g})"
        )
    return base


class TkGameplayEditorApp21(TkConsoleNavigationEditorApp21):
    """Production SwirEditor shell with project input/rebinding and settings UI."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        gameplay: EditorGameplayTooling21,
        **kwargs: Any,
    ) -> None:
        self.gameplay_controller = EditorGameplayPanelController21(gameplay)
        self._gameplay_window: Any | None = None
        self._gameplay_action_tree: Any | None = None
        self._gameplay_binding_tree: Any | None = None
        self._gameplay_action_iids: dict[str, str] = {}
        self._gameplay_binding_indices: dict[str, int] = {}
        self._gameplay_display_vars: dict[str, Any] = {}
        self._gameplay_accessibility_vars: dict[str, Any] = {}
        self._gameplay_conflict_var: Any | None = None
        self._gameplay_dirty_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        gameplay = self.tk.Menu(menu, tearoff=False)
        gameplay.add_command(label="Input & Settings…", command=self._open_gameplay_panel)
        menu.add_cascade(label="Gameplay", menu=gameplay)

    def _open_gameplay_panel(self) -> None:
        if self._gameplay_window is not None and self._gameplay_window.winfo_exists():
            self._gameplay_window.deiconify()
            self._gameplay_window.lift()
            self._gameplay_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — Gameplay Input & Settings")
        window.geometry("920x650")
        window.minsize(760, 540)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_gameplay_panel)
        self._gameplay_window = window

        notebook = self.ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 8))

        input_tab = self.ttk.Frame(notebook, padding=10)
        display_tab = self.ttk.Frame(notebook, padding=10)
        accessibility_tab = self.ttk.Frame(notebook, padding=10)
        notebook.add(input_tab, text="Input / Rebinding")
        notebook.add(display_tab, text="Display")
        notebook.add(accessibility_tab, text="Accessibility")

        self._build_input_tab(input_tab)
        self._build_display_tab(display_tab)
        self._build_accessibility_tab(accessibility_tab)

        footer = self.ttk.Frame(window, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        self._gameplay_dirty_var = self.tk.StringVar()
        self.ttk.Label(footer, textvariable=self._gameplay_dirty_var).pack(side="left")
        self.ttk.Button(footer, text="Reload Saved", command=self._reload_gameplay).pack(
            side="right", padx=(6, 0)
        )
        self.ttk.Button(footer, text="Close", command=self._close_gameplay_panel).pack(side="right")

        self._refresh_gameplay_panel(refresh_settings=True)

    def _build_input_tab(self, parent: Any) -> None:
        parent.columnconfigure(0, weight=2)
        parent.columnconfigure(1, weight=5)
        parent.rowconfigure(0, weight=1)

        action_frame = self.ttk.LabelFrame(parent, text="Actions", padding=6)
        action_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        action_frame.rowconfigure(0, weight=1)
        action_frame.columnconfigure(0, weight=1)
        action_tree = self.ttk.Treeview(
            action_frame,
            columns=("action",),
            show="headings",
            selectmode="browse",
        )
        action_tree.heading("action", text="Semantic action")
        action_tree.column("action", width=180, stretch=True)
        action_tree.grid(row=0, column=0, sticky="nsew")
        action_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_gameplay_bindings())
        self._gameplay_action_tree = action_tree

        binding_frame = self.ttk.LabelFrame(parent, text="Bindings", padding=6)
        binding_frame.grid(row=0, column=1, sticky="nsew")
        binding_frame.rowconfigure(0, weight=1)
        binding_frame.columnconfigure(0, weight=1)
        binding_tree = self.ttk.Treeview(
            binding_frame,
            columns=("kind", "control", "details"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("kind", "Kind", 120),
            ("control", "Control", 130),
            ("details", "Details", 300),
        ):
            binding_tree.heading(column, text=title)
            binding_tree.column(column, width=width, stretch=column == "details")
        binding_tree.grid(row=0, column=0, sticky="nsew")
        self._gameplay_binding_tree = binding_tree

        controls = self.ttk.Frame(parent)
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        buttons = (
            ("New Action + Key…", self._new_action_key),
            ("Add Key…", self._add_key_binding),
            ("Add Mouse…", self._add_mouse_binding),
            ("Add Gamepad Button…", self._add_gamepad_button_binding),
            ("Add Gamepad Axis…", self._add_gamepad_axis_binding),
            ("Remove Binding", self._remove_binding),
            ("Reset Action", self._reset_action),
        )
        for index, (label, command) in enumerate(buttons):
            self.ttk.Button(controls, text=label, command=command).grid(
                row=index // 4,
                column=index % 4,
                sticky="ew",
                padx=(0, 6),
                pady=(0, 6),
            )
        for column in range(4):
            controls.columnconfigure(column, weight=1)

        self._gameplay_conflict_var = self.tk.StringVar()
        self.ttk.Label(
            parent,
            textvariable=self._gameplay_conflict_var,
            wraplength=760,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    def _build_display_tab(self, parent: Any) -> None:
        frame = self.ttk.LabelFrame(parent, text="Project display defaults", padding=12)
        frame.pack(fill="x")
        fields = (
            ("width", "Width", "text"),
            ("height", "Height", "text"),
            ("fullscreen", "Fullscreen", "bool"),
            ("borderless", "Borderless", "bool"),
            ("vsync", "VSync", "bool"),
            ("max_fps", "Max FPS (0 = unlimited)", "text"),
            ("ui_scale", "UI scale", "text"),
        )
        for row, (name, label, kind) in enumerate(fields):
            self.ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if kind == "bool":
                variable = self.tk.BooleanVar()
                widget = self.ttk.Checkbutton(frame, variable=variable)
            else:
                variable = self.tk.StringVar()
                widget = self.ttk.Entry(frame, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            self._gameplay_display_vars[name] = variable
        frame.columnconfigure(1, weight=1)
        self.ttk.Button(parent, text="Apply Display Defaults", command=self._apply_display).pack(
            anchor="e", pady=(10, 0)
        )

    def _build_accessibility_tab(self, parent: Any) -> None:
        frame = self.ttk.LabelFrame(parent, text="Project accessibility defaults", padding=12)
        frame.pack(fill="x")
        fields = (
            ("text_scale", "Text scale", "text"),
            ("reduced_motion", "Reduced motion", "bool"),
            ("high_contrast", "High contrast", "bool"),
            ("subtitles", "Subtitles", "bool"),
            ("hold_to_confirm", "Hold to confirm", "bool"),
        )
        for row, (name, label, kind) in enumerate(fields):
            self.ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if kind == "bool":
                variable = self.tk.BooleanVar()
                widget = self.ttk.Checkbutton(frame, variable=variable)
            else:
                variable = self.tk.StringVar()
                widget = self.ttk.Entry(frame, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            self._gameplay_accessibility_vars[name] = variable
        frame.columnconfigure(1, weight=1)
        actions = self.ttk.Frame(parent)
        actions.pack(fill="x", pady=(10, 0))
        self.ttk.Button(
            actions,
            text="Reset All Settings",
            command=self._reset_game_settings,
        ).pack(side="left")
        self.ttk.Button(
            actions,
            text="Apply Accessibility Defaults",
            command=self._apply_accessibility,
        ).pack(side="right")

    def _selected_gameplay_action(self) -> str | None:
        tree = self._gameplay_action_tree
        if tree is None:
            return None
        selection = tree.selection()
        if not selection:
            return None
        values = tree.item(selection[0], "values")
        return str(values[0]) if values else None

    def _refresh_gameplay_panel(self, *, refresh_settings: bool = False) -> None:
        tree = self._gameplay_action_tree
        if tree is None:
            return
        selected = self._selected_gameplay_action()
        frame = self.gameplay_controller.frame(selected)
        tree.delete(*tree.get_children())
        self._gameplay_action_iids.clear()
        for index, action in enumerate(frame.actions):
            iid = f"gameplay-action-{index}"
            tree.insert("", "end", iid=iid, values=(action,))
            self._gameplay_action_iids[action] = iid
        selected = frame.selected_action
        if selected is not None and selected in self._gameplay_action_iids:
            iid = self._gameplay_action_iids[selected]
            tree.selection_set(iid)
            tree.focus(iid)
        self._refresh_gameplay_bindings()
        if refresh_settings:
            self._set_gameplay_settings_vars(frame.settings)
        if self._gameplay_dirty_var is not None:
            state = "unsaved changes" if frame.dirty else "saved"
            self._gameplay_dirty_var.set(
                f"Gameplay config: {state} · changes persist with File → Save Project"
            )
        if self._gameplay_conflict_var is not None:
            text = "No binding conflicts detected."
            if frame.conflicts:
                text = "Shared controls: " + " · ".join(frame.conflicts)
            self._gameplay_conflict_var.set(text)

    def _refresh_gameplay_bindings(self) -> None:
        tree = self._gameplay_binding_tree
        if tree is None:
            return
        action = self._selected_gameplay_action()
        frame = self.gameplay_controller.frame(action)
        tree.delete(*tree.get_children())
        self._gameplay_binding_indices.clear()
        for row in frame.bindings:
            iid = f"gameplay-binding-{row.index}"
            binding = row.binding
            details = ""
            if binding.kind == "gamepad_button":
                details = f"pad={binding.gamepad_id}"
            elif binding.kind == "gamepad_axis":
                details = (
                    f"pad={binding.gamepad_id}, dir={binding.direction}, "
                    f"threshold={binding.threshold:g}, scale={binding.scale:g}"
                )
            tree.insert("", "end", iid=iid, values=(binding.kind, binding.control, details))
            self._gameplay_binding_indices[iid] = row.index

    def _set_gameplay_settings_vars(self, settings: GameSettings) -> None:
        display = settings.display
        for name in ("width", "height", "max_fps", "ui_scale"):
            self._gameplay_display_vars[name].set(str(getattr(display, name)))
        for name in ("fullscreen", "borderless", "vsync"):
            self._gameplay_display_vars[name].set(bool(getattr(display, name)))
        accessibility = settings.accessibility
        self._gameplay_accessibility_vars["text_scale"].set(str(accessibility.text_scale))
        for name in ("reduced_motion", "high_contrast", "subtitles", "hold_to_confirm"):
            self._gameplay_accessibility_vars[name].set(bool(getattr(accessibility, name)))

    def _run_gameplay_action(
        self,
        title: str,
        action: Any,
        *,
        refresh_settings: bool = False,
    ) -> None:
        try:
            action()
        except (IndexError, OSError, TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))
            self.messagebox.showerror(title, str(exc), parent=self._gameplay_window or self.root)
            return
        self.status_var.set(self.gameplay_controller.status)
        self._refresh_gameplay_panel(refresh_settings=refresh_settings)

    def _new_action_key(self) -> None:
        from tkinter import simpledialog

        action = simpledialog.askstring(
            "New Action",
            "Semantic action name:",
            parent=self._gameplay_window,
        )
        if not action:
            return
        key = simpledialog.askstring(
            "New Action",
            "Initial keyboard key:",
            parent=self._gameplay_window,
        )
        if key:
            clean_action = action.strip()
            self._run_gameplay_action(
                "New Action",
                lambda: self.gameplay_controller.add_key(clean_action, key.strip()),
            )
            iid = self._gameplay_action_iids.get(clean_action)
            if iid is not None and self._gameplay_action_tree is not None:
                self._gameplay_action_tree.selection_set(iid)
                self._gameplay_action_tree.focus(iid)
                self._refresh_gameplay_bindings()

    def _add_key_binding(self) -> None:
        from tkinter import simpledialog

        action = self._selected_gameplay_action()
        if action is None:
            return
        key = simpledialog.askstring("Add Key", "Keyboard key:", parent=self._gameplay_window)
        if key:
            self._run_gameplay_action(
                "Add Key",
                lambda: self.gameplay_controller.add_key(action, key.strip()),
            )

    def _add_mouse_binding(self) -> None:
        from tkinter import simpledialog

        action = self._selected_gameplay_action()
        if action is None:
            return
        button = simpledialog.askinteger(
            "Add Mouse Button",
            "Mouse button number (0–31):",
            minvalue=0,
            maxvalue=31,
            parent=self._gameplay_window,
        )
        if button is not None:
            self._run_gameplay_action(
                "Add Mouse Button",
                lambda: self.gameplay_controller.add_mouse_button(action, button),
            )

    def _add_gamepad_button_binding(self) -> None:
        from tkinter import simpledialog

        action = self._selected_gameplay_action()
        if action is None:
            return
        button = simpledialog.askstring(
            "Add Gamepad Button",
            "Gamepad button (for example A, B, X, START):",
            parent=self._gameplay_window,
        )
        if not button:
            return
        gamepad_id = simpledialog.askinteger(
            "Add Gamepad Button",
            "Gamepad ID (0–15):",
            initialvalue=0,
            minvalue=0,
            maxvalue=15,
            parent=self._gameplay_window,
        )
        if gamepad_id is not None:
            self._run_gameplay_action(
                "Add Gamepad Button",
                lambda: self.gameplay_controller.add_gamepad_button(
                    action,
                    button.strip(),
                    gamepad_id=gamepad_id,
                ),
            )

    def _add_gamepad_axis_binding(self) -> None:
        from tkinter import simpledialog

        action = self._selected_gameplay_action()
        if action is None:
            return
        axis = simpledialog.askstring(
            "Add Gamepad Axis",
            "Gamepad axis (for example LEFT_X or LEFT_Y):",
            parent=self._gameplay_window,
        )
        if not axis:
            return
        direction = simpledialog.askinteger(
            "Add Gamepad Axis",
            "Direction (-1, 0 or 1):",
            initialvalue=0,
            minvalue=-1,
            maxvalue=1,
            parent=self._gameplay_window,
        )
        if direction is None:
            return
        self._run_gameplay_action(
            "Add Gamepad Axis",
            lambda: self.gameplay_controller.add_gamepad_axis(
                action,
                axis.strip(),
                direction=direction,
            ),
        )

    def _remove_binding(self) -> None:
        action = self._selected_gameplay_action()
        tree = self._gameplay_binding_tree
        if action is None or tree is None:
            return
        selection = tree.selection()
        if not selection:
            return
        index = self._gameplay_binding_indices.get(selection[0])
        if index is None:
            return
        self._run_gameplay_action(
            "Remove Binding",
            lambda: self.gameplay_controller.remove_binding(action, index),
        )

    def _reset_action(self) -> None:
        action = self._selected_gameplay_action()
        if action is not None:
            self._run_gameplay_action(
                "Reset Action",
                lambda: self.gameplay_controller.reset_action(action),
            )

    def _apply_display(self) -> None:
        values = self._gameplay_display_vars

        def apply() -> None:
            self.gameplay_controller.update_display(
                width=int(values["width"].get()),
                height=int(values["height"].get()),
                fullscreen=bool(values["fullscreen"].get()),
                borderless=bool(values["borderless"].get()),
                vsync=bool(values["vsync"].get()),
                max_fps=int(values["max_fps"].get()),
                ui_scale=float(values["ui_scale"].get()),
            )

        self._run_gameplay_action("Display Defaults", apply, refresh_settings=True)

    def _apply_accessibility(self) -> None:
        values = self._gameplay_accessibility_vars

        def apply() -> None:
            self.gameplay_controller.update_accessibility(
                text_scale=float(values["text_scale"].get()),
                reduced_motion=bool(values["reduced_motion"].get()),
                high_contrast=bool(values["high_contrast"].get()),
                subtitles=bool(values["subtitles"].get()),
                hold_to_confirm=bool(values["hold_to_confirm"].get()),
            )

        self._run_gameplay_action("Accessibility Defaults", apply, refresh_settings=True)

    def _reset_game_settings(self) -> None:
        self._run_gameplay_action(
            "Reset Game Settings",
            self.gameplay_controller.reset_settings,
            refresh_settings=True,
        )

    def _reload_gameplay(self) -> None:
        if self.gameplay_controller.tooling.dirty:
            discard = self.messagebox.askyesno(
                "Reload Gameplay Configuration",
                "Discard unsaved gameplay input/settings changes and reload saved files?",
                parent=self._gameplay_window,
            )
            if not discard:
                return
        self._run_gameplay_action(
            "Reload Gameplay Configuration",
            self.gameplay_controller.reload,
            refresh_settings=True,
        )

    def _close_gameplay_panel(self) -> None:
        window, self._gameplay_window = self._gameplay_window, None
        if window is not None and window.winfo_exists():
            window.destroy()
        self._gameplay_action_tree = None
        self._gameplay_binding_tree = None
        self._gameplay_action_iids.clear()
        self._gameplay_binding_indices.clear()
        self._gameplay_display_vars.clear()
        self._gameplay_accessibility_vars.clear()
        self._gameplay_conflict_var = None
        self._gameplay_dirty_var = None