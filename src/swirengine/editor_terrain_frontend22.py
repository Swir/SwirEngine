from __future__ import annotations

from typing import Any

from .editor_terrain22 import (
    EditorTerrainError22,
    EditorTerrainPanelController22,
    EditorTerrainTooling22,
)
from .editor_visual_scripting_frontend22 import TkVisualScriptEditorApp22


class TkTerrainEditorApp22(TkVisualScriptEditorApp22):
    """Unified SwirEditor shell with mouse-driven runtime-backed terrain authoring."""

    def __init__(
        self,
        controller: Any,
        *,
        terrains: EditorTerrainTooling22,
        **kwargs: Any,
    ) -> None:
        self.terrain_controller = EditorTerrainPanelController22(terrains)
        self._terrain_window: Any | None = None
        self._terrain_list: Any | None = None
        self._terrain_canvas: Any | None = None
        self._terrain_status_var: Any | None = None
        self._terrain_path_var: Any | None = None
        self._terrain_width_var: Any | None = None
        self._terrain_height_var: Any | None = None
        self._terrain_mode_var: Any | None = None
        self._terrain_radius_var: Any | None = None
        self._terrain_strength_var: Any | None = None
        self._terrain_layer_var: Any | None = None
        self._terrain_foliage_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        world_menu = self.tk.Menu(menu, tearoff=False)
        world_menu.add_command(label="World / Terrain Authoring…", command=self._open_terrain_editor)
        menu.add_cascade(label="World", menu=world_menu)

    def _open_terrain_editor(self) -> None:
        if self._terrain_window is not None and self._terrain_window.winfo_exists():
            self._terrain_window.deiconify()
            self._terrain_window.lift()
            return
        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor 2.2 — World / Terrain Authoring")
        window.geometry("1180x760")
        window.minsize(940, 620)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_terrain_editor)
        self._terrain_window = window

        body = self.ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        create = self.ttk.Frame(body)
        create.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self._terrain_path_var = self.tk.StringVar(value="world/main.swirterrain")
        self._terrain_width_var = self.tk.StringVar(value="65")
        self._terrain_height_var = self.tk.StringVar(value="65")
        self.ttk.Label(create, text="Asset").grid(row=0, column=0, sticky="w")
        self.ttk.Entry(create, textvariable=self._terrain_path_var, width=34).grid(
            row=0, column=1, padx=(6, 12)
        )
        self.ttk.Label(create, text="W").grid(row=0, column=2)
        self.ttk.Entry(create, textvariable=self._terrain_width_var, width=6).grid(
            row=0, column=3, padx=(4, 8)
        )
        self.ttk.Label(create, text="H").grid(row=0, column=4)
        self.ttk.Entry(create, textvariable=self._terrain_height_var, width=6).grid(
            row=0, column=5, padx=(4, 8)
        )
        self.ttk.Button(create, text="Create Terrain", command=self._terrain_create).grid(
            row=0, column=6
        )

        left = self.ttk.Frame(body)
        left.grid(row=1, column=0, sticky="nsw", padx=(0, 10))
        self.ttk.Label(left, text="Terrain Assets").pack(anchor="w")
        self._terrain_list = self.tk.Listbox(left, width=30, height=20, exportselection=False)
        self._terrain_list.pack(fill="both", expand=True, pady=(4, 10))
        self._terrain_list.bind("<<ListboxSelect>>", self._terrain_select)

        brush = self.ttk.LabelFrame(left, text="Brush / Placement", padding=8)
        brush.pack(fill="x")
        self._terrain_mode_var = self.tk.StringVar(value="raise")
        self._terrain_radius_var = self.tk.StringVar(value="4.0")
        self._terrain_strength_var = self.tk.StringVar(value="1.0")
        self._terrain_layer_var = self.tk.StringVar(value="1")
        self._terrain_foliage_var = self.tk.StringVar(value="assets/trees/tree.glb")
        self.ttk.Combobox(
            brush,
            textvariable=self._terrain_mode_var,
            values=("raise", "lower", "flatten", "smooth", "paint", "foliage"),
            state="readonly",
            width=12,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.ttk.Label(brush, text="Radius").grid(row=1, column=0, sticky="w")
        self.ttk.Entry(brush, textvariable=self._terrain_radius_var, width=9).grid(row=1, column=1)
        self.ttk.Label(brush, text="Strength").grid(row=2, column=0, sticky="w")
        self.ttk.Entry(brush, textvariable=self._terrain_strength_var, width=9).grid(row=2, column=1)
        self.ttk.Label(brush, text="Paint layer").grid(row=3, column=0, sticky="w")
        self.ttk.Entry(brush, textvariable=self._terrain_layer_var, width=9).grid(row=3, column=1)
        self.ttk.Label(brush, text="Foliage asset").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.ttk.Entry(brush, textvariable=self._terrain_foliage_var, width=26).grid(
            row=5, column=0, columnspan=2, sticky="ew"
        )

        right = self.ttk.Frame(body)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self._terrain_canvas = self.tk.Canvas(
            right,
            background="#10151d",
            highlightthickness=1,
            highlightbackground="#344152",
            cursor="crosshair",
        )
        self._terrain_canvas.grid(row=0, column=0, sticky="nsew")
        self._terrain_canvas.bind("<Button-1>", self._terrain_canvas_click)
        self._terrain_canvas.bind("<B1-Motion>", self._terrain_canvas_click)
        self._terrain_status_var = self.tk.StringVar(value=self.terrain_controller.status)
        self.ttk.Label(right, textvariable=self._terrain_status_var, wraplength=820).grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )

        actions = self.ttk.Frame(body)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for index, (label, command) in enumerate(
            (
                ("Undo", self._terrain_undo),
                ("Redo", self._terrain_redo),
                ("Runtime Preview", self._terrain_runtime_preview),
                ("Reload", self._terrain_reload),
                ("Save", self._terrain_save),
            )
        ):
            self.ttk.Button(actions, text=label, command=command).grid(
                row=0, column=index, sticky="ew", padx=(0, 6)
            )
            actions.columnconfigure(index, weight=1)
        self._refresh_terrain_editor()

    def _close_terrain_editor(self) -> None:
        if self._terrain_window is not None:
            self._terrain_window.destroy()
        self._terrain_window = None

    def _terrain_create(self) -> None:
        try:
            assert self._terrain_path_var is not None
            assert self._terrain_width_var is not None
            assert self._terrain_height_var is not None
            self.terrain_controller.create(
                self._terrain_path_var.get().strip(),
                width=int(self._terrain_width_var.get()),
                height=int(self._terrain_height_var.get()),
            )
            self._refresh_terrain_editor()
        except (EditorTerrainError22, ValueError) as exc:
            self.messagebox.showerror("Terrain authoring", str(exc), parent=self._terrain_window)

    def _terrain_select(self, _event: Any = None) -> None:
        if self._terrain_list is None:
            return
        selected = self._terrain_list.curselection()
        if not selected:
            return
        try:
            self.terrain_controller.select(str(self._terrain_list.get(selected[0])))
            self._refresh_terrain_editor()
        except (EditorTerrainError22, ValueError, OSError) as exc:
            self.messagebox.showerror("Terrain authoring", str(exc), parent=self._terrain_window)

    def _terrain_canvas_click(self, event: Any) -> None:
        try:
            document = self.terrain_controller.tooling.selected_document()
            assert self._terrain_canvas is not None
            assert self._terrain_mode_var is not None
            assert self._terrain_radius_var is not None
            assert self._terrain_strength_var is not None
            width = max(1, self._terrain_canvas.winfo_width())
            height = max(1, self._terrain_canvas.winfo_height())
            runtime = document.runtime_preview()
            x = min(runtime.world_width, max(0.0, event.x / width * runtime.world_width))
            z = min(runtime.world_depth, max(0.0, event.y / height * runtime.world_depth))
            mode = self._terrain_mode_var.get()
            radius = float(self._terrain_radius_var.get())
            strength = float(self._terrain_strength_var.get())
            if mode == "paint":
                assert self._terrain_layer_var is not None
                self.terrain_controller.paint(
                    int(self._terrain_layer_var.get()),
                    x=x,
                    z=z,
                    radius=radius,
                    strength=strength,
                )
            elif mode == "foliage":
                assert self._terrain_foliage_var is not None
                self.terrain_controller.add_foliage(
                    self._terrain_foliage_var.get().strip(),
                    x=x,
                    z=z,
                )
            else:
                self.terrain_controller.sculpt(
                    x=x,
                    z=z,
                    radius=radius,
                    strength=strength,
                    mode=mode,
                )
            self._refresh_terrain_editor()
        except (EditorTerrainError22, ValueError) as exc:
            self.messagebox.showerror("Terrain authoring", str(exc), parent=self._terrain_window)

    def _terrain_undo(self) -> None:
        self._terrain_action(self.terrain_controller.undo)

    def _terrain_redo(self) -> None:
        self._terrain_action(self.terrain_controller.redo)

    def _terrain_reload(self) -> None:
        self._terrain_action(self.terrain_controller.reload)

    def _terrain_save(self) -> None:
        self._terrain_action(self.terrain_controller.save)

    def _terrain_runtime_preview(self) -> None:
        try:
            preview = self.terrain_controller.runtime_preview()
            if self._terrain_status_var is not None:
                self._terrain_status_var.set(
                    f"{self.terrain_controller.status} · "
                    f"{preview.world_width:.1f}×{preview.world_depth:.1f} world units · "
                    f"active/preload {preview.active_radius_chunks}/{preview.preload_radius_chunks}"
                )
        except (EditorTerrainError22, ValueError) as exc:
            self.messagebox.showerror("Terrain authoring", str(exc), parent=self._terrain_window)

    def _terrain_action(self, action: Any) -> None:
        try:
            action()
            self._refresh_terrain_editor()
        except (EditorTerrainError22, ValueError, OSError) as exc:
            self.messagebox.showerror("Terrain authoring", str(exc), parent=self._terrain_window)

    def _refresh_terrain_editor(self) -> None:
        snapshot = self.terrain_controller.snapshot()
        if self._terrain_list is not None:
            self._terrain_list.delete(0, self.tk.END)
            for index, path in enumerate(snapshot.asset_paths):
                self._terrain_list.insert(self.tk.END, path)
                if path == snapshot.selected:
                    self._terrain_list.selection_set(index)
        if self._terrain_status_var is not None:
            suffix = " · unsaved" if snapshot.dirty else ""
            self._terrain_status_var.set(self.terrain_controller.status + suffix)
        self._draw_terrain()

    def _draw_terrain(self) -> None:
        canvas = self._terrain_canvas
        if canvas is None:
            return
        canvas.delete("all")
        snapshot = self.terrain_controller.snapshot()
        if snapshot.selected is None:
            canvas.create_text(20, 20, anchor="nw", fill="#9fb0c4", text="Create or select a terrain asset")
            return
        document = self.terrain_controller.tooling.selected_document()
        heights = document.asset.heights
        rows, columns = heights.shape
        canvas.update_idletasks()
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        stride = max(1, max(rows, columns) // 64)
        minimum = float(heights.min())
        maximum = float(heights.max())
        span = max(1e-6, maximum - minimum)
        for row in range(0, rows, stride):
            for column in range(0, columns, stride):
                value = float(heights[row, column])
                level = int(36 + 180 * (value - minimum) / span)
                fill = f"#{level:02x}{level:02x}{level:02x}"
                x0 = column / columns * width
                y0 = row / rows * height
                x1 = min(width, (column + stride) / columns * width + 1)
                y1 = min(height, (row + stride) / rows * height + 1)
                canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="")
        chunk_cells = document.asset.config.chunk_cells
        for dirty in document.asset.dirty_chunks():
            x0 = dirty.x * chunk_cells / max(1, columns - 1) * width
            y0 = dirty.z * chunk_cells / max(1, rows - 1) * height
            x1 = min(width, (dirty.x + 1) * chunk_cells / max(1, columns - 1) * width)
            y1 = min(height, (dirty.z + 1) * chunk_cells / max(1, rows - 1) * height)
            canvas.create_rectangle(x0, y0, x1, y1, outline="#ffb454", width=2)
