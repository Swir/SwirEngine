from __future__ import annotations

import ast
import base64
import time
from dataclasses import dataclass
from typing import Any

from .editor_assets import EditorAssetBrowser, EditorAssetBrowserFrame
from .editor_diagnostics import (
    EditorConsole,
    EditorConsoleFrame,
    EditorProfiler,
    EditorProfilerFrame,
)
from .editor_preview import EditorPreviewFrame, EditorPreviewSession
from .editor_runtime import EditorRuntimeMode
from .editor_workspace import EditorPanelState, EditorShellFrame, EditorWorkspace


@dataclass(frozen=True, slots=True)
class FrontendHierarchyRow:
    key: str
    label: str
    kind: str
    type_name: str
    depth: int
    enabled: bool
    selected: bool


@dataclass(frozen=True, slots=True)
class FrontendInspectorRow:
    name: str
    value: object
    display_value: str
    type_name: str
    editable: bool


@dataclass(frozen=True, slots=True)
class EditorFrontendFrame:
    """Toolkit-neutral snapshot consumed by the interactive desktop front-end."""

    shell: EditorShellFrame
    hierarchy: tuple[FrontendHierarchyRow, ...]
    inspector_fields: tuple[FrontendInspectorRow, ...]
    assets: EditorAssetBrowserFrame | None
    console: EditorConsoleFrame | None
    profiler: EditorProfilerFrame | None
    preview: EditorPreviewFrame | None = None
    status: str = "Ready"


def parse_editor_value(text: str, current: object) -> object:
    """Convert an inspector text edit to a value compatible with the current field.

    Strings intentionally stay strings without requiring Python quotes. Primitive containers use
    ``ast.literal_eval`` so the desktop editor can edit useful values without executing code.
    """

    raw = text.strip()
    if isinstance(current, str):
        return text
    if isinstance(current, bool):
        normalized = raw.casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise ValueError("boolean values must be true/false, yes/no, on/off or 1/0")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(raw, 0)
    if isinstance(current, float):
        return float(raw)
    if current is None:
        if raw.casefold() in {"none", "null"}:
            return None
        return ast.literal_eval(raw)
    if isinstance(current, (tuple, list, set, dict)):
        value = ast.literal_eval(raw)
        expected = type(current)
        if not isinstance(value, expected):
            raise TypeError(f"expected {expected.__name__}, got {type(value).__name__}")
        return value
    value = ast.literal_eval(raw)
    if isinstance(value, type(current)):
        return value
    raise TypeError(f"expected {type(current).__name__}, got {type(value).__name__}")


class EditorFrontendController:
    """Interactive adapter joining workspace, preview, assets and diagnostics into one UI contract."""

    def __init__(
        self,
        workspace: EditorWorkspace,
        *,
        asset_browser: EditorAssetBrowser | None = None,
        console: EditorConsole | None = None,
        profiler: EditorProfiler | None = None,
        preview: EditorPreviewSession | None = None,
    ) -> None:
        if not isinstance(workspace, EditorWorkspace):
            raise TypeError("workspace must be an EditorWorkspace")
        if preview is not None and preview.workspace is not workspace:
            raise ValueError("preview workspace must match controller workspace")
        self.workspace = workspace
        self.asset_browser = asset_browser
        self.console = console
        self.profiler = profiler
        self.preview = preview
        self._status = "Ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self) -> EditorFrontendFrame:
        shell = self.workspace.frame()
        selected_key = None if shell.inspector is None else shell.inspector.key
        hierarchy = tuple(
            FrontendHierarchyRow(
                item.key,
                item.label,
                item.kind,
                item.type_name,
                item.depth,
                item.enabled,
                item.key == selected_key,
            )
            for item in shell.hierarchy
        )
        fields: tuple[FrontendInspectorRow, ...] = ()
        if shell.inspector is not None:
            fields = tuple(
                FrontendInspectorRow(
                    field.name,
                    field.value,
                    self._display_value(field.value),
                    field.type_name,
                    field.editable,
                )
                for field in shell.inspector.fields
            )
        return EditorFrontendFrame(
            shell,
            hierarchy,
            fields,
            None if self.asset_browser is None else self.asset_browser.frame(),
            None if self.console is None else self.console.frame(limit=250),
            None if self.profiler is None else self.profiler.frame(),
            None if self.preview is None else self.preview.frame(),
            self._status,
        )

    def select(self, key: str | None) -> object | None:
        selected = self.workspace.select(key)
        self._status = "Selection cleared" if key is None else f"Selected {key}"
        return selected

    def set_hierarchy_query(self, query: str) -> None:
        self.workspace.set_hierarchy_filter(query)
        self._status = "Hierarchy filter updated"

    def edit_property(self, name: str, text: str) -> object:
        snapshot = self.workspace.inspector.inspect()
        if snapshot is None:
            raise RuntimeError("no scene object is selected")
        field = next((item for item in snapshot.fields if item.name == name), None)
        if field is None:
            raise KeyError(f"unknown inspector field {name!r}")
        if not field.editable:
            raise ValueError(f"inspector field {name!r} is read-only")
        value = parse_editor_value(text, field.value)
        edit = self.workspace.inspector.set_property(name, value)
        self._status = f"Changed {name}"
        return edit.after

    def undo(self) -> bool:
        edit = self.workspace.undo()
        if edit is None:
            self._status = "Nothing to undo"
            return False
        self._status = "Undo"
        return True

    def redo(self) -> bool:
        edit = self.workspace.redo()
        if edit is None:
            self._status = "Nothing to redo"
            return False
        self._status = "Redo"
        return True

    def set_gizmo(self, mode: str) -> None:
        self.workspace.configure_viewport(gizmo=mode)
        self._status = f"Gizmo: {mode}"

    def set_snap(self, enabled: bool) -> None:
        self.workspace.configure_viewport(snap_enabled=enabled)
        self._status = "Snapping enabled" if enabled else "Snapping disabled"

    def set_panel_visible(self, panel_id: str, visible: bool) -> EditorPanelState:
        panel = self.workspace.configure_panel(panel_id, visible=visible)
        self._status = f"{panel.title}: {'shown' if visible else 'hidden'}"
        return panel

    def set_asset_query(self, query: str) -> EditorAssetBrowserFrame | None:
        if self.asset_browser is None:
            return None
        frame = self.asset_browser.set_filter(query)
        self._status = f"Assets: {frame.visible_files} visible"
        return frame

    def refresh_assets(self) -> EditorAssetBrowserFrame | None:
        if self.asset_browser is None:
            return None
        frame = self.asset_browser.refresh()
        self._status = f"Assets refreshed: {frame.total_files} files"
        return frame

    def play_pause(self) -> EditorRuntimeMode | None:
        if self.preview is None:
            self._status = "Runtime preview not attached"
            return None
        mode = self.preview.play_pause()
        self._status = {
            EditorRuntimeMode.EDIT: "Edit",
            EditorRuntimeMode.PLAYING: "Playing",
            EditorRuntimeMode.PAUSED: "Paused",
        }[mode]
        return mode

    def stop(self) -> bool:
        if self.preview is None:
            self._status = "Runtime preview not attached"
            return False
        stopped = self.preview.stop()
        self._status = "Stopped" if stopped else "Already in Edit mode"
        return stopped

    def step(self, dt: float | None = None) -> bool:
        if self.preview is None:
            self._status = "Runtime preview not attached"
            return False
        stepped = self.preview.step(dt)
        self._status = "Stepped one runtime frame" if stepped else "Unable to step runtime"
        return stepped

    def update_runtime(self, dt: float) -> bool:
        if self.preview is None:
            return False
        return self.preview.update(dt)

    def capture_viewport(self, width: int, height: int) -> bool:
        if self.preview is None:
            return False
        return self.preview.capture(width, height) is not None

    @staticmethod
    def _display_value(value: object) -> str:
        if isinstance(value, str):
            return value
        return repr(value)


class TkEditorApp:
    """Dependency-free desktop front-end for :class:`EditorWorkspace`.

    Tk is imported lazily so servers and CI can use every editor model without requiring a window
    system. When an :class:`EditorPreviewSession` is attached, the editor also owns Play/Pause/Stop/
    Step controls and embeds live RGB frames read from the engine renderer framebuffer.
    """

    def __init__(
        self,
        controller: EditorFrontendController,
        *,
        title: str | None = None,
        refresh_ms: int = 250,
    ) -> None:
        if not isinstance(controller, EditorFrontendController):
            raise TypeError("controller must be an EditorFrontendController")
        if refresh_ms < 16:
            raise ValueError("refresh_ms must be >= 16")
        try:
            import tkinter as tk
            from tkinter import messagebox, ttk
        except ImportError as exc:  # pragma: no cover - platform packaging detail
            raise RuntimeError("Tkinter is required for the desktop visual editor") from exc

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.controller = controller
        self.refresh_ms = int(refresh_ms)
        self.root = tk.Tk()
        project = controller.workspace.project_name
        self.root.title(title or f"SwirEngine Editor — {project}")
        self.root.geometry("1400x850")
        self.root.minsize(960, 600)
        self._closed = False
        self._hierarchy_keys: dict[str, str] = {}
        self._field_entries: dict[str, Any] = {}
        self._viewport_photo: Any = None
        self._last_refresh_time = time.perf_counter()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.root.destroy()

    def refresh(self) -> None:
        if self._closed:
            return
        now = time.perf_counter()
        dt = max(0.0, now - self._last_refresh_time)
        self._last_refresh_time = now
        self.controller.update_runtime(dt)
        if self.controller.preview is not None and self.controller.preview.viewport is not None:
            width = max(1, self.viewport_label.winfo_width())
            height = max(1, self.viewport_label.winfo_height())
            self.controller.capture_viewport(width, height)
        frame = self.controller.frame()
        self._refresh_toolbar(frame)
        self._refresh_hierarchy(frame)
        self._refresh_inspector(frame)
        self._refresh_viewport(frame)
        self._refresh_assets(frame)
        self._refresh_console(frame)
        self._refresh_profiler(frame)
        self.status_var.set(frame.status)
        self.root.after(self.refresh_ms, self.refresh)

    def _build(self) -> None:
        ttk = self.ttk
        tk = self.tk

        toolbar = ttk.Frame(self.root, padding=(6, 5))
        toolbar.pack(fill="x")
        self.undo_button = ttk.Button(toolbar, text="Undo", command=self._undo)
        self.undo_button.pack(side="left")
        self.redo_button = ttk.Button(toolbar, text="Redo", command=self._redo)
        self.redo_button.pack(side="left", padx=(4, 12))
        self.play_button = ttk.Button(toolbar, text="Play", command=self._play_pause)
        self.play_button.pack(side="left", padx=(0, 4))
        self.stop_button = ttk.Button(toolbar, text="Stop", command=self._stop)
        self.stop_button.pack(side="left")
        self.step_button = ttk.Button(toolbar, text="Step", command=self._step)
        self.step_button.pack(side="left", padx=(4, 12))
        for mode in ("translate", "rotate", "scale"):
            ttk.Button(toolbar, text=mode.title(), command=lambda value=mode: self._gizmo(value)).pack(
                side="left", padx=2
            )
        self.snap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Snap", variable=self.snap_var, command=self._snap).pack(
            side="left", padx=(10, 0)
        )

        vertical = ttk.Panedwindow(self.root, orient="vertical")
        vertical.pack(fill="both", expand=True)
        upper = ttk.Panedwindow(vertical, orient="horizontal")
        bottom = ttk.Notebook(vertical)
        vertical.add(upper, weight=4)
        vertical.add(bottom, weight=1)

        hierarchy_panel = ttk.Frame(upper, padding=6)
        center_panel = ttk.Frame(upper, padding=6)
        inspector_panel = ttk.Frame(upper, padding=6)
        upper.add(hierarchy_panel, weight=1)
        upper.add(center_panel, weight=4)
        upper.add(inspector_panel, weight=1)

        ttk.Label(hierarchy_panel, text="Hierarchy").pack(anchor="w")
        self.hierarchy_query = tk.StringVar()
        search = ttk.Entry(hierarchy_panel, textvariable=self.hierarchy_query)
        search.pack(fill="x", pady=(4, 6))
        search.bind("<KeyRelease>", self._hierarchy_search)
        self.hierarchy_tree = ttk.Treeview(hierarchy_panel, show="tree", selectmode="browse")
        self.hierarchy_tree.pack(fill="both", expand=True)
        self.hierarchy_tree.bind("<<TreeviewSelect>>", self._hierarchy_select)

        self.viewport_label = ttk.Label(center_panel, text="Viewport", anchor="center")
        self.viewport_label.pack(fill="both", expand=True)

        ttk.Label(inspector_panel, text="Inspector").pack(anchor="w")
        self.inspector_canvas = tk.Canvas(inspector_panel, highlightthickness=0)
        self.inspector_scroll = ttk.Scrollbar(
            inspector_panel, orient="vertical", command=self.inspector_canvas.yview
        )
        self.inspector_body = ttk.Frame(self.inspector_canvas)
        self.inspector_body.bind(
            "<Configure>",
            lambda _event: self.inspector_canvas.configure(
                scrollregion=self.inspector_canvas.bbox("all")
            ),
        )
        self.inspector_canvas.create_window((0, 0), window=self.inspector_body, anchor="nw")
        self.inspector_canvas.configure(yscrollcommand=self.inspector_scroll.set)
        self.inspector_canvas.pack(side="left", fill="both", expand=True)
        self.inspector_scroll.pack(side="right", fill="y")

        self.assets_tab = ttk.Frame(bottom, padding=6)
        self.console_tab = ttk.Frame(bottom, padding=6)
        self.profiler_tab = ttk.Frame(bottom, padding=6)
        bottom.add(self.assets_tab, text="Assets")
        bottom.add(self.console_tab, text="Console")
        bottom.add(self.profiler_tab, text="Profiler")

        asset_header = ttk.Frame(self.assets_tab)
        asset_header.pack(fill="x")
        self.asset_query = tk.StringVar()
        asset_search = ttk.Entry(asset_header, textvariable=self.asset_query)
        asset_search.pack(side="left", fill="x", expand=True)
        asset_search.bind("<KeyRelease>", self._asset_search)
        ttk.Button(asset_header, text="Refresh", command=self._asset_refresh).pack(
            side="left", padx=(6, 0)
        )
        self.assets_tree = ttk.Treeview(
            self.assets_tab, columns=("kind", "size"), show="tree headings"
        )
        self.assets_tree.heading("#0", text="Asset")
        self.assets_tree.heading("kind", text="Type")
        self.assets_tree.heading("size", text="Bytes")
        self.assets_tree.pack(fill="both", expand=True, pady=(6, 0))

        self.console_text = tk.Text(self.console_tab, height=8, wrap="none", state="disabled")
        self.console_text.pack(fill="both", expand=True)
        self.profiler_label = ttk.Label(self.profiler_tab, justify="left", anchor="nw")
        self.profiler_label.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(6, 3)).pack(fill="x")

    def _refresh_toolbar(self, frame: EditorFrontendFrame) -> None:
        self.undo_button.configure(state="normal" if frame.shell.can_undo else "disabled")
        self.redo_button.configure(state="normal" if frame.shell.can_redo else "disabled")
        self.snap_var.set(frame.shell.viewport.snap_enabled)
        if frame.preview is None:
            self.play_button.configure(text="Play", state="disabled")
            self.stop_button.configure(state="disabled")
            self.step_button.configure(state="disabled")
            return
        mode = frame.preview.runtime.mode
        self.play_button.configure(
            text="Pause" if mode is EditorRuntimeMode.PLAYING else "Play",
            state="normal",
        )
        self.stop_button.configure(
            state="disabled" if mode is EditorRuntimeMode.EDIT else "normal"
        )
        self.step_button.configure(state="normal")

    def _refresh_hierarchy(self, frame: EditorFrontendFrame) -> None:
        selected = next((row.key for row in frame.hierarchy if row.selected), None)
        self.hierarchy_tree.delete(*self.hierarchy_tree.get_children())
        self._hierarchy_keys.clear()
        parents: dict[str, str] = {}
        for index, row in enumerate(frame.shell.hierarchy):
            parent_iid = ""
            if row.parent_key is not None:
                parent_iid = parents.get(row.parent_key, "")
            iid = f"h{index}"
            marker = "" if row.enabled else " [disabled]"
            self.hierarchy_tree.insert(parent_iid, "end", iid=iid, text=f"{row.label}{marker}")
            self._hierarchy_keys[iid] = row.key
            parents[row.key] = iid
            if row.key == selected:
                self.hierarchy_tree.selection_set(iid)
                self.hierarchy_tree.see(iid)

    def _refresh_inspector(self, frame: EditorFrontendFrame) -> None:
        for child in self.inspector_body.winfo_children():
            child.destroy()
        self._field_entries.clear()
        if frame.shell.inspector is None:
            self.ttk.Label(self.inspector_body, text="Nothing selected").grid(row=0, column=0)
            return
        self.ttk.Label(
            self.inspector_body,
            text=frame.shell.inspector.type_name,
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        for row_index, field in enumerate(frame.inspector_fields, start=1):
            self.ttk.Label(self.inspector_body, text=field.name).grid(
                row=row_index, column=0, sticky="w", padx=(0, 6), pady=2
            )
            entry = self.ttk.Entry(self.inspector_body)
            entry.insert(0, field.display_value)
            entry.grid(row=row_index, column=1, sticky="ew", pady=2)
            if not field.editable:
                entry.configure(state="disabled")
            else:
                entry.bind(
                    "<Return>",
                    lambda _event, name=field.name, widget=entry: self._commit_property(name, widget),
                )
                entry.bind(
                    "<FocusOut>",
                    lambda _event, name=field.name, widget=entry: self._commit_property(name, widget),
                )
            self._field_entries[field.name] = entry
        self.inspector_body.columnconfigure(1, weight=1)

    def _refresh_viewport(self, frame: EditorFrontendFrame) -> None:
        if frame.preview is not None and frame.preview.image is not None:
            data = base64.b64encode(frame.preview.image.to_ppm()).decode("ascii")
            self._viewport_photo = self.tk.PhotoImage(data=data, format="PPM")
            self.viewport_label.configure(image=self._viewport_photo, text="", compound="center")
            return
        self._viewport_photo = None
        selected = "No selection"
        if frame.shell.inspector is not None:
            selected = frame.shell.inspector.type_name
        vp = frame.shell.viewport
        runtime = "Edit"
        if frame.preview is not None:
            runtime = frame.preview.runtime.mode.value.title()
        self.viewport_label.configure(
            image="",
            text=(
                f"SwirEngine Viewport ({vp.mode.upper()})\n\n"
                f"Runtime: {runtime}\nSelected: {selected}\nGizmo: {vp.gizmo}\n"
                f"Snap: {'on' if vp.snap_enabled else 'off'}\n\n"
                "Attach RendererViewportBridge for live framebuffer preview."
            ),
        )

    def _refresh_assets(self, frame: EditorFrontendFrame) -> None:
        self.assets_tree.delete(*self.assets_tree.get_children())
        if frame.assets is None:
            return
        for index, asset in enumerate(frame.assets.entries):
            self.assets_tree.insert(
                "",
                "end",
                iid=f"a{index}",
                text=asset.relative_path,
                values=(asset.kind, asset.size_bytes),
            )

    def _refresh_console(self, frame: EditorFrontendFrame) -> None:
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", "end")
        if frame.console is not None:
            for entry in frame.console.entries:
                self.console_text.insert(
                    "end", f"[{entry.level.upper():8}] {entry.source}: {entry.message}\n"
                )
        self.console_text.configure(state="disabled")

    def _refresh_profiler(self, frame: EditorFrontendFrame) -> None:
        if frame.profiler is None:
            self.profiler_label.configure(text="Profiler not attached")
            return
        profile = frame.profiler
        self.profiler_label.configure(
            text=(
                f"Samples: {profile.sample_count}\n"
                f"FPS: {profile.latest.fps:.1f}\n"
                f"Frame: {profile.latest.frame_ms:.2f} ms\n"
                f"CPU: {profile.latest.cpu_ms:.2f} ms\n"
                f"Peak frame: {profile.peak_frame_ms:.2f} ms\n"
                f"Budget: {profile.frame_budget_ms:.2f} ms\n"
                f"Over budget: {profile.over_budget_frames}"
            )
        )

    def _hierarchy_search(self, _event: object = None) -> None:
        self.controller.set_hierarchy_query(self.hierarchy_query.get())

    def _hierarchy_select(self, _event: object = None) -> None:
        selection = self.hierarchy_tree.selection()
        if not selection:
            return
        key = self._hierarchy_keys.get(selection[0])
        if key is not None:
            self.controller.select(key)

    def _commit_property(self, name: str, widget: Any) -> None:
        try:
            self.controller.edit_property(name, widget.get())
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))

    def _undo(self) -> None:
        self.controller.undo()

    def _redo(self) -> None:
        self.controller.redo()

    def _play_pause(self) -> None:
        self.controller.play_pause()

    def _stop(self) -> None:
        self.controller.stop()

    def _step(self) -> None:
        try:
            self.controller.step()
        except ValueError as exc:
            self.status_var.set(str(exc))

    def _gizmo(self, mode: str) -> None:
        self.controller.set_gizmo(mode)

    def _snap(self) -> None:
        self.controller.set_snap(bool(self.snap_var.get()))

    def _asset_search(self, _event: object = None) -> None:
        self.controller.set_asset_query(self.asset_query.get())

    def _asset_refresh(self) -> None:
        self.controller.refresh_assets()


def launch_editor(
    workspace: EditorWorkspace,
    *,
    asset_browser: EditorAssetBrowser | None = None,
    console: EditorConsole | None = None,
    profiler: EditorProfiler | None = None,
    preview: EditorPreviewSession | None = None,
    title: str | None = None,
) -> None:
    """Launch the built-in Tk desktop editor for an existing workspace."""

    controller = EditorFrontendController(
        workspace,
        asset_browser=asset_browser,
        console=console,
        profiler=profiler,
        preview=preview,
    )
    TkEditorApp(controller, title=title).run()
