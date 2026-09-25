from __future__ import annotations

from typing import Any

from .editor_animation_workspace_frontend22 import TkAnimationMachineEditorApp22
from .editor_vfx22 import EditorVFXPanelController22
from .vfx_authoring22 import EditorVFXTooling22


class TkVFXEditorApp22(TkAnimationMachineEditorApp22):
    """Integrated SwirEditor shell exposing Particle/VFX authoring and preview controls."""

    def __init__(
        self,
        controller: Any,
        *,
        vfx: EditorVFXTooling22,
        **kwargs: Any,
    ) -> None:
        self.vfx_controller = EditorVFXPanelController22(vfx)
        self._vfx_window: Any | None = None
        self._vfx_list: Any | None = None
        self._vfx_name_var: Any | None = None
        self._vfx_preset_var: Any | None = None
        self._vfx_capacity_var: Any | None = None
        self._vfx_rate_var: Any | None = None
        self._vfx_status_var: Any | None = None
        self._vfx_diagnostics: Any | None = None
        self._vfx_tick_after: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        vfx_menu = self.tk.Menu(menu, tearoff=False)
        vfx_menu.add_command(label="Particle / VFX Editor…", command=self._open_vfx_editor)
        menu.add_cascade(label="VFX", menu=vfx_menu)

    def _open_vfx_editor(self) -> None:
        if self._vfx_window is not None and self._vfx_window.winfo_exists():
            self._vfx_window.deiconify()
            self._vfx_window.lift()
            return
        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor 2.2 — Particle / VFX Editor")
        window.geometry("1040x680")
        window.minsize(860, 560)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_vfx_editor)
        self._vfx_window = window

        body = self.ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        toolbar = self.ttk.Frame(body)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self._vfx_name_var = self.tk.StringVar(value="impact")
        self._vfx_preset_var = self.tk.StringVar(value="soft-smoke-2d")
        self.ttk.Label(toolbar, text="Effect").pack(side="left")
        self.ttk.Entry(toolbar, textvariable=self._vfx_name_var, width=24).pack(
            side="left", padx=(6, 10)
        )
        self.ttk.Combobox(
            toolbar,
            textvariable=self._vfx_preset_var,
            values=tuple(item.name for item in self.vfx_controller.presets),
            state="readonly",
            width=18,
        ).pack(side="left")
        self.ttk.Button(toolbar, text="New", command=self._vfx_create).pack(
            side="left", padx=(8, 0)
        )
        self.ttk.Button(toolbar, text="Apply Preset", command=self._vfx_apply_preset).pack(
            side="left", padx=(6, 0)
        )
        self.ttk.Button(toolbar, text="Save", command=self._vfx_save).pack(side="right")
        self.ttk.Button(toolbar, text="Validate", command=self._vfx_validate).pack(
            side="right", padx=(0, 6)
        )

        left = self.ttk.Frame(body)
        left.grid(row=1, column=0, sticky="nsw", padx=(0, 12))
        self.ttk.Label(left, text="VFX Effects").pack(anchor="w")
        self._vfx_list = self.tk.Listbox(left, width=28, height=22, exportselection=False)
        self._vfx_list.pack(fill="both", expand=True, pady=(4, 10))
        self._vfx_list.bind("<<ListboxSelect>>", self._vfx_select)

        controls = self.ttk.LabelFrame(left, text="Emitter", padding=8)
        controls.pack(fill="x")
        self._vfx_capacity_var = self.tk.StringVar(value="128")
        self._vfx_rate_var = self.tk.StringVar(value="20.0")
        self.ttk.Label(controls, text="Capacity").grid(row=0, column=0, sticky="w")
        self.ttk.Entry(controls, textvariable=self._vfx_capacity_var, width=10).grid(
            row=0, column=1, padx=(6, 0)
        )
        self.ttk.Label(controls, text="Rate / s").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.ttk.Entry(controls, textvariable=self._vfx_rate_var, width=10).grid(
            row=1, column=1, padx=(6, 0), pady=(6, 0)
        )
        self.ttk.Button(controls, text="Apply", command=self._vfx_apply_common).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        right = self.ttk.Frame(body)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        preview = self.ttk.LabelFrame(right, text="Runtime Preview", padding=8)
        preview.grid(row=0, column=0, sticky="ew")
        for label, command in (
            ("Start", self._vfx_start),
            ("Pause", self._vfx_pause),
            ("Step 1/60", self._vfx_step),
            ("Burst 32", self._vfx_burst),
            ("Clear", self._vfx_clear),
        ):
            self.ttk.Button(preview, text=label, command=command).pack(side="left", padx=(0, 6))

        self._vfx_diagnostics = self.tk.Text(right, wrap="word", state="disabled")
        self._vfx_diagnostics.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self._vfx_status_var = self.tk.StringVar(value="Particle/VFX Editor ready")
        self.ttk.Label(right, textvariable=self._vfx_status_var).grid(
            row=2, column=0, sticky="ew", pady=(8, 0)
        )
        self._refresh_vfx_editor()

    def _close_vfx_editor(self) -> None:
        self._cancel_vfx_tick()
        if self._vfx_window is not None:
            self._vfx_window.destroy()
        self._vfx_window = None

    def _vfx_create(self) -> None:
        try:
            name = self._value(self._vfx_name_var)
            if not name:
                raise ValueError("VFX effect name cannot be empty")
            self.vfx_controller.create(name, preset=self._value(self._vfx_preset_var))
            self._refresh_vfx_editor()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._vfx_error(exc)

    def _vfx_select(self, _event: Any = None) -> None:
        if self._vfx_list is None:
            return
        selected = self._vfx_list.curselection()
        if not selected:
            return
        try:
            name = str(self._vfx_list.get(selected[0]))
            self.vfx_controller.select(name)
            if self._vfx_name_var is not None:
                self._vfx_name_var.set(name)
            self._refresh_vfx_editor()
        except (RuntimeError, TypeError, ValueError) as exc:
            self._vfx_error(exc)

    def _vfx_apply_preset(self) -> None:
        self._vfx_action(lambda: self.vfx_controller.apply_preset(self._value(self._vfx_preset_var)))

    def _vfx_apply_common(self) -> None:
        self._vfx_action(
            lambda: self.vfx_controller.update_common(
                capacity=int(self._value(self._vfx_capacity_var)),
                rate=float(self._value(self._vfx_rate_var)),
            )
        )

    def _vfx_save(self) -> None:
        self._vfx_action(self.vfx_controller.save)

    def _vfx_validate(self) -> None:
        try:
            self._set_vfx_status(" | ".join(self.vfx_controller.validate()))
            self._refresh_vfx_editor()
        except (RuntimeError, TypeError, ValueError) as exc:
            self._vfx_error(exc)

    def _vfx_start(self) -> None:
        self._vfx_action(self.vfx_controller.start_preview)
        self._schedule_vfx_tick()

    def _vfx_pause(self) -> None:
        self._cancel_vfx_tick()
        self._vfx_action(self.vfx_controller.pause_preview)

    def _vfx_step(self) -> None:
        self._vfx_action(lambda: self.vfx_controller.step_preview(1.0 / 60.0))

    def _vfx_burst(self) -> None:
        self._vfx_action(lambda: self.vfx_controller.burst(32))

    def _vfx_clear(self) -> None:
        self._vfx_action(self.vfx_controller.clear_preview)

    def _schedule_vfx_tick(self) -> None:
        if self._vfx_tick_after is None and self._vfx_window is not None:
            self._vfx_tick_after = self.root.after(16, self._vfx_tick)

    def _cancel_vfx_tick(self) -> None:
        if self._vfx_tick_after is None:
            return
        try:
            self.root.after_cancel(self._vfx_tick_after)
        except (RuntimeError, TypeError, ValueError):
            pass
        self._vfx_tick_after = None

    def _vfx_tick(self) -> None:
        self._vfx_tick_after = None
        if not self.vfx_controller.frame().preview_running:
            return
        try:
            self.vfx_controller.step_preview(1.0 / 60.0)
            self._refresh_vfx_editor()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.vfx_controller.pause_preview()
            self._vfx_error(exc)
            return
        self._schedule_vfx_tick()

    def _vfx_action(self, action: Any) -> None:
        try:
            action()
            self._refresh_vfx_editor()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._vfx_error(exc)

    def _refresh_vfx_editor(self) -> None:
        frame = self.vfx_controller.frame()
        if self._vfx_list is not None:
            self._vfx_list.delete(0, "end")
            for name in frame.effect_names:
                self._vfx_list.insert("end", name)
        if frame.selected is not None:
            spec = self.vfx_controller.selected_spec()
            if self._vfx_capacity_var is not None:
                self._vfx_capacity_var.set(str(spec.capacity))
            if self._vfx_rate_var is not None:
                self._vfx_rate_var.set(str(spec.rate))
        lines = [
            f"Selected: {frame.selected or '(none)'}",
            f"Backend: {frame.backend or '(none)'}",
            f"Dirty: {'yes' if frame.dirty else 'no'}",
            f"Preview: {'running' if frame.preview_running else 'paused/stopped'}",
        ]
        lines.extend(frame.messages)
        if frame.diagnostics is not None:
            d = frame.diagnostics
            lines.extend(
                (
                    "",
                    "Runtime diagnostics",
                    f"capacity={d.capacity}",
                    f"active_or_queued={d.active_or_queued}",
                    f"emitted={d.emitted_total}",
                    f"submitted={d.submitted_total}",
                    f"recycled={d.recycled_total}",
                    f"work_visits_or_frames={d.work_visits_or_frames}",
                    f"last_step={d.last_step:.4f}s",
                    f"step_clamped={'yes' if d.step_was_clamped else 'no'}",
                )
            )
        self._write_vfx_diagnostics("\n".join(lines))
        self._set_vfx_status(self.vfx_controller.status)

    def _write_vfx_diagnostics(self, text: str) -> None:
        if self._vfx_diagnostics is None:
            return
        self._vfx_diagnostics.configure(state="normal")
        self._vfx_diagnostics.delete("1.0", "end")
        self._vfx_diagnostics.insert("1.0", text)
        self._vfx_diagnostics.configure(state="disabled")

    def _set_vfx_status(self, text: str) -> None:
        if self._vfx_status_var is not None:
            self._vfx_status_var.set(text)

    def _vfx_error(self, exc: Exception) -> None:
        self._set_vfx_status(str(exc))
        self.messagebox.showerror("Particle / VFX Editor", str(exc), parent=self._vfx_window)

    @staticmethod
    def _value(variable: Any) -> str:
        if variable is None:
            raise RuntimeError("VFX editor is not open")
        return str(variable.get()).strip()
