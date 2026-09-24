from __future__ import annotations

from typing import Any

from .editor_animation_workspace22 import AnimationMachineWorkspace22
from .editor_terrain_frontend22 import TkTerrainEditorApp22


class TkAnimationMachineEditorApp22(TkTerrainEditorApp22):
    """Integrated SwirEditor shell exposing the M5 animation graph workspace."""

    def __init__(
        self,
        controller: Any,
        *,
        animation_machines: AnimationMachineWorkspace22,
        **kwargs: Any,
    ) -> None:
        self.animation_machines = animation_machines
        self._anim_window: Any | None = None
        self._anim_asset_var: Any | None = None
        self._anim_asset_list: Any | None = None
        self._anim_canvas: Any | None = None
        self._anim_status_var: Any | None = None
        self._anim_details: Any | None = None
        self._anim_drag_state: str | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        animation_menu = self.tk.Menu(menu, tearoff=False)
        animation_menu.add_command(
            label="State Machine / Blend Tree…",
            command=self._open_animation_machine_editor,
        )
        menu.add_cascade(label="Animation", menu=animation_menu)

    def _open_animation_machine_editor(self) -> None:
        if self._anim_window is not None and self._anim_window.winfo_exists():
            self._anim_window.deiconify()
            self._anim_window.lift()
            return
        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor 2.2 — Animation State Machine / Blend Tree")
        window.geometry("1240x760")
        window.minsize(980, 620)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_animation_machine_editor)
        self._anim_window = window

        body = self.ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        toolbar = self.ttk.Frame(body)
        toolbar.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._anim_asset_var = self.tk.StringVar(value="player.swiranimgraph")
        self.ttk.Label(toolbar, text="Graph asset").pack(side="left")
        self.ttk.Entry(toolbar, textvariable=self._anim_asset_var, width=34).pack(
            side="left", padx=(6, 8)
        )
        self.ttk.Button(toolbar, text="New", command=self._anim_create).pack(side="left")
        self.ttk.Button(toolbar, text="Open", command=self._anim_open_named).pack(
            side="left", padx=(6, 0)
        )
        self.ttk.Button(toolbar, text="Save", command=self._anim_save).pack(
            side="left", padx=(6, 0)
        )
        self.ttk.Button(toolbar, text="Validate Runtime", command=self._anim_validate).pack(
            side="right"
        )

        assets = self.ttk.Frame(body)
        assets.grid(row=1, column=0, sticky="nsw", padx=(0, 10))
        self.ttk.Label(assets, text="Animation Graphs").pack(anchor="w")
        self._anim_asset_list = self.tk.Listbox(
            assets,
            width=30,
            height=24,
            exportselection=False,
        )
        self._anim_asset_list.pack(fill="both", expand=True, pady=(4, 0))
        self._anim_asset_list.bind("<Double-Button-1>", self._anim_open_selected)

        graph = self.ttk.Frame(body)
        graph.grid(row=1, column=1, sticky="nsew")
        graph.columnconfigure(0, weight=1)
        graph.rowconfigure(0, weight=1)
        self._anim_canvas = self.tk.Canvas(
            graph,
            background="#0f141d",
            highlightthickness=1,
            highlightbackground="#344152",
        )
        self._anim_canvas.grid(row=0, column=0, sticky="nsew")
        self._anim_canvas.bind("<ButtonPress-1>", self._anim_drag_begin)
        self._anim_canvas.bind("<B1-Motion>", self._anim_drag_move)
        self._anim_canvas.bind("<ButtonRelease-1>", self._anim_drag_end)

        details_frame = self.ttk.Frame(body)
        details_frame.grid(row=1, column=2, sticky="nse", padx=(10, 0))
        self.ttk.Label(details_frame, text="Parameters / Transitions").pack(anchor="w")
        self._anim_details = self.tk.Text(
            details_frame,
            width=36,
            height=24,
            wrap="word",
            state="disabled",
        )
        self._anim_details.pack(fill="both", expand=True, pady=(4, 0))

        footer = self.ttk.Frame(body)
        footer.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._anim_status_var = self.tk.StringVar(value="Animation workspace ready")
        self.ttk.Label(footer, textvariable=self._anim_status_var).pack(
            side="left", fill="x", expand=True
        )
        self.ttk.Button(footer, text="Start Preview", command=self._anim_start_preview).pack(
            side="right"
        )
        self.ttk.Button(footer, text="Step 1/60", command=self._anim_step_preview).pack(
            side="right", padx=(0, 6)
        )
        self._refresh_animation_machine_editor()

    def _close_animation_machine_editor(self) -> None:
        if self._anim_window is not None:
            self._anim_window.destroy()
        self._anim_window = None
        self._anim_drag_state = None

    def _anim_create(self) -> None:
        try:
            name = self._animation_asset_name()
            self.animation_machines.create(name)
            self._set_animation_status(f"Created {name}; bind clips before runtime preview")
            self._refresh_animation_machine_editor()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._animation_error(exc)

    def _anim_open_named(self) -> None:
        try:
            name = self._animation_asset_name()
            self.animation_machines.open(name)
            self._set_animation_status(f"Opened {name}")
            self._refresh_animation_machine_editor()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._animation_error(exc)

    def _anim_open_selected(self, _event: Any = None) -> None:
        if self._anim_asset_list is None:
            return
        selected = self._anim_asset_list.curselection()
        if not selected:
            return
        assert self._anim_asset_var is not None
        self._anim_asset_var.set(str(self._anim_asset_list.get(selected[0])))
        self._anim_open_named()

    def _anim_save(self) -> None:
        try:
            frame = self.animation_machines.save()
            self._set_animation_status(f"Saved {frame.asset_name}")
            self._refresh_animation_machine_editor()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._animation_error(exc)

    def _anim_validate(self) -> None:
        try:
            issues = self.animation_machines.validate_runtime()
            if issues:
                self._set_animation_status("Runtime validation: " + " | ".join(issues))
            else:
                self._set_animation_status("Runtime validation passed")
        except (RuntimeError, TypeError, ValueError) as exc:
            self._animation_error(exc)

    def _anim_start_preview(self) -> None:
        try:
            frame = self.animation_machines.start_preview()
            self._set_animation_status(f"Preview started: {frame.preview_state}")
            self._draw_animation_graph(frame)
        except (RuntimeError, TypeError, ValueError) as exc:
            self._animation_error(exc)

    def _anim_step_preview(self) -> None:
        try:
            frame = self.animation_machines.controller.step_preview(1.0 / 60.0)
            self._set_animation_status(
                f"Preview: {frame.preview_state} @ {frame.preview_normalized_time or 0.0:.3f}"
            )
            self._draw_animation_graph(frame)
        except (RuntimeError, TypeError, ValueError) as exc:
            self._animation_error(exc)

    def _anim_drag_begin(self, event: Any) -> None:
        if self._anim_canvas is None:
            return
        closest = self._anim_canvas.find_closest(event.x, event.y)
        if not closest:
            return
        tags = self._anim_canvas.gettags(closest[0])
        self._anim_drag_state = next(
            (tag.removeprefix("state:") for tag in tags if tag.startswith("state:")),
            None,
        )

    def _anim_drag_move(self, event: Any) -> None:
        if self._anim_drag_state is None:
            return
        try:
            frame = self.animation_machines.controller.move_state(
                self._anim_drag_state,
                float(event.x),
                float(event.y),
            )
            self._draw_animation_graph(frame)
            self._set_animation_status(f"Moved {self._anim_drag_state}")
        except (RuntimeError, TypeError, ValueError, KeyError) as exc:
            self._animation_error(exc)
            self._anim_drag_state = None

    def _anim_drag_end(self, _event: Any) -> None:
        self._anim_drag_state = None

    def _refresh_animation_machine_editor(self) -> None:
        if self._anim_asset_list is not None:
            self._anim_asset_list.delete(0, "end")
            for asset in self.animation_machines.discover():
                self._anim_asset_list.insert("end", asset)
        try:
            frame = self.animation_machines.controller.frame()
        except RuntimeError:
            if self._anim_canvas is not None:
                self._anim_canvas.delete("all")
                self._anim_canvas.create_text(
                    30,
                    30,
                    anchor="nw",
                    fill="#9fb0c6",
                    text="Create or open a .swiranimgraph asset to begin.",
                )
            self._write_animation_details("No animation graph open.")
            return
        self._draw_animation_graph(frame)
        lines = ["Parameters:"]
        lines.extend(
            f"  {item.name}: {item.kind} = {item.default!r}" for item in frame.parameters
        )
        if not frame.parameters:
            lines.append("  (none)")
        lines.append("\nTransitions:")
        lines.extend(
            f"  {item.index}: {item.source} -> {item.target}"
            + (f" [{', '.join(item.conditions)}]" if item.conditions else "")
            for item in frame.transitions
        )
        if not frame.transitions:
            lines.append("  (none)")
        if frame.diagnostics:
            lines.append("\nDiagnostics:")
            lines.extend(f"  ! {item}" for item in frame.diagnostics)
        self._write_animation_details("\n".join(lines))

    def _draw_animation_graph(self, frame: Any) -> None:
        if self._anim_canvas is None:
            return
        canvas = self._anim_canvas
        canvas.delete("all")
        positions = {state.name: (state.x, state.y) for state in frame.states}
        for transition in frame.transitions:
            if transition.source == "*":
                continue
            source = positions.get(transition.source)
            target = positions.get(transition.target)
            if source is None or target is None:
                continue
            canvas.create_line(
                source[0],
                source[1],
                target[0],
                target[1],
                fill="#7389a7",
                width=2,
                arrow="last",
            )
        for state in frame.states:
            x, y = state.x, state.y
            tag = f"state:{state.name}"
            outline = "#8ecbff" if state.name == frame.preview_state else "#4f6684"
            width = 3 if state.initial else 2
            canvas.create_rectangle(
                x - 70,
                y - 28,
                x + 70,
                y + 28,
                fill="#172235",
                outline=outline,
                width=width,
                tags=(tag,),
            )
            canvas.create_text(
                x,
                y - 5,
                fill="#eef5ff",
                text=state.name,
                tags=(tag,),
            )
            canvas.create_text(
                x,
                y + 13,
                fill="#9fb0c6",
                text=state.motion,
                tags=(tag,),
            )

    def _animation_asset_name(self) -> str:
        if self._anim_asset_var is None:
            raise RuntimeError("animation workspace is not open")
        name = self._anim_asset_var.get().strip()
        if not name:
            raise ValueError("animation graph asset name cannot be empty")
        return name

    def _write_animation_details(self, text: str) -> None:
        if self._anim_details is None:
            return
        self._anim_details.configure(state="normal")
        self._anim_details.delete("1.0", "end")
        self._anim_details.insert("1.0", text)
        self._anim_details.configure(state="disabled")

    def _set_animation_status(self, text: str) -> None:
        if self._anim_status_var is not None:
            self._anim_status_var.set(text)

    def _animation_error(self, exc: Exception) -> None:
        self._set_animation_status(str(exc))
        self.messagebox.showerror(
            "Animation State Machine",
            str(exc),
            parent=self._anim_window,
        )
