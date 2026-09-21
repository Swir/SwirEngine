from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .animation15 import AnimationPose, InterpolationMode
from .editor_animation_tooling21 import EditorAnimationTooling21, EditorAnimationToolingError
from .editor_gameplay_frontend21 import TkGameplayEditorApp21
from .editor_viewport_frontend21 import EditorProductionViewportController21


@dataclass(frozen=True, slots=True)
class AnimationTrackRow21:
    binding: str
    interpolation: str
    keyframe_count: int
    first_time: float
    last_time: float


@dataclass(frozen=True, slots=True)
class AnimationPanelFrame21:
    path: str | None
    name: str | None
    duration: float | None
    loop: bool
    dirty: bool
    tracks: tuple[AnimationTrackRow21, ...]
    preview_time: float | None
    preview_values: tuple[tuple[str, Any], ...]


def parse_animation_value21(text: str) -> Any:
    """Parse a portable animation value from strict JSON text."""

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"animation value must be valid JSON: {exc.msg}") from exc
    if isinstance(value, dict):
        raise ValueError("animation values may not be JSON objects")
    return value


class EditorAnimationPanelController21:
    """Toolkit-neutral creator adapter over :class:`EditorAnimationTooling21`."""

    def __init__(self, tooling: EditorAnimationTooling21) -> None:
        if not isinstance(tooling, EditorAnimationTooling21):
            raise TypeError("tooling must be an EditorAnimationTooling21")
        self.tooling = tooling
        self._preview_time: float | None = None
        self._preview_pose: AnimationPose | None = None
        self._status = "Animation tooling ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self) -> AnimationPanelFrame21:
        snapshot = self.tooling.snapshot()
        clip = snapshot.clip
        tracks = tuple(
            AnimationTrackRow21(
                binding=item.binding,
                interpolation=item.interpolation,
                keyframe_count=item.keyframe_count,
                first_time=item.first_time,
                last_time=item.last_time,
            )
            for item in snapshot.tracks
        )
        preview_values: tuple[tuple[str, Any], ...] = ()
        if self._preview_pose is not None:
            preview_values = tuple(sorted(self._preview_pose.values.items()))
        return AnimationPanelFrame21(
            path=snapshot.path,
            name=None if clip is None else clip.name,
            duration=None if clip is None else clip.duration,
            loop=snapshot.loop,
            dirty=snapshot.dirty,
            tracks=tracks,
            preview_time=self._preview_time,
            preview_values=preview_values,
        )

    def new_clip(
        self,
        name: str,
        *,
        duration: float = 1.0,
        loop: bool = True,
        path: str | None = None,
    ) -> AnimationPanelFrame21:
        self.tooling.new_clip(name, duration=duration, loop=loop, path=path)
        self._clear_preview()
        self._status = f"Created animation clip {name}"
        return self.frame()

    def load(self, path: str) -> AnimationPanelFrame21:
        self.tooling.load(path)
        self._clear_preview()
        self._status = f"Loaded animation asset {path}"
        return self.frame()

    def save(self) -> AnimationPanelFrame21:
        snapshot = self.tooling.save()
        self._status = f"Saved animation asset {snapshot.path}"
        return self.frame()

    def rename_clip(self, name: str) -> AnimationPanelFrame21:
        self.tooling.rename_clip(name)
        self._status = f"Renamed animation clip to {name}"
        return self.frame()

    def set_duration(self, duration: float) -> AnimationPanelFrame21:
        self.tooling.set_duration(duration)
        self._clear_preview()
        self._status = "Updated animation duration"
        return self.frame()

    def set_loop(self, loop: bool) -> AnimationPanelFrame21:
        self.tooling.set_loop(loop)
        self._clear_preview()
        self._status = "Updated animation loop mode"
        return self.frame()

    def add_track(
        self,
        binding: str,
        *,
        initial_value: Any = 0.0,
        interpolation: InterpolationMode | str = InterpolationMode.LINEAR,
    ) -> AnimationPanelFrame21:
        self.tooling.add_track(
            binding,
            initial_value=initial_value,
            interpolation=interpolation,
        )
        self._clear_preview()
        self._status = f"Added animation track {binding}"
        return self.frame()

    def remove_track(self, binding: str) -> AnimationPanelFrame21:
        self.tooling.remove_track(binding)
        self._clear_preview()
        self._status = f"Removed animation track {binding}"
        return self.frame()

    def set_interpolation(
        self,
        binding: str,
        interpolation: InterpolationMode | str,
    ) -> AnimationPanelFrame21:
        self.tooling.set_interpolation(binding, interpolation)
        self._clear_preview()
        self._status = f"Updated interpolation for {binding}"
        return self.frame()

    def set_keyframe(
        self,
        binding: str,
        time: float,
        value: Any,
    ) -> AnimationPanelFrame21:
        self.tooling.set_keyframe(binding, time, value)
        self._clear_preview()
        self._status = f"Set keyframe on {binding} at {float(time):g}s"
        return self.frame()

    def remove_keyframe(self, binding: str, time: float) -> AnimationPanelFrame21:
        self.tooling.remove_keyframe(binding, time)
        self._clear_preview()
        self._status = f"Removed keyframe on {binding} at {float(time):g}s"
        return self.frame()

    def sample(self, time: float) -> AnimationPanelFrame21:
        time = float(time)
        self._preview_pose = self.tooling.sample(time)
        self._preview_time = time
        self._status = f"Previewed animation at {time:g}s"
        return self.frame()

    def _clear_preview(self) -> None:
        self._preview_time = None
        self._preview_pose = None


class TkAnimationEditorApp21(TkGameplayEditorApp21):
    """Production SwirEditor shell with an integrated animation clip editor."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        animation: EditorAnimationTooling21,
        **kwargs: Any,
    ) -> None:
        self.animation_controller = EditorAnimationPanelController21(animation)
        self._animation_window: Any | None = None
        self._animation_track_tree: Any | None = None
        self._animation_path_var: Any | None = None
        self._animation_name_var: Any | None = None
        self._animation_duration_var: Any | None = None
        self._animation_loop_var: Any | None = None
        self._animation_preview_time_var: Any | None = None
        self._animation_preview_var: Any | None = None
        self._animation_status_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        animation = self.tk.Menu(menu, tearoff=False)
        animation.add_command(label="Clip Editor…", command=self._open_animation_panel)
        menu.add_cascade(label="Animation", menu=animation)

    def _open_animation_panel(self) -> None:
        if self._animation_window is not None and self._animation_window.winfo_exists():
            self._animation_window.deiconify()
            self._animation_window.lift()
            self._animation_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — Animation Clip Editor")
        window.geometry("940x620")
        window.minsize(760, 500)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_animation_panel)
        self._animation_window = window

        header = self.ttk.LabelFrame(window, text="Clip", padding=10)
        header.pack(fill="x", padx=12, pady=(12, 8))
        self._animation_path_var = self.tk.StringVar()
        self._animation_name_var = self.tk.StringVar()
        self._animation_duration_var = self.tk.StringVar(value="1.0")
        self._animation_loop_var = self.tk.BooleanVar(value=True)
        self._animation_preview_time_var = self.tk.StringVar(value="0.0")
        fields = (
            ("Asset", self._animation_path_var),
            ("Name", self._animation_name_var),
            ("Duration", self._animation_duration_var),
        )
        for row, (label, variable) in enumerate(fields):
            self.ttk.Label(header, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                pady=3,
            )
            self.ttk.Entry(header, textvariable=variable).grid(
                row=row,
                column=1,
                columnspan=5,
                sticky="ew",
                pady=3,
            )
        self.ttk.Checkbutton(
            header,
            text="Loop",
            variable=self._animation_loop_var,
        ).grid(row=3, column=0, sticky="w", pady=(6, 0))
        for column in range(6):
            header.columnconfigure(column, weight=1 if column == 1 else 0)

        buttons = self.ttk.Frame(header)
        buttons.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        for label, command in (
            ("New", self._animation_new),
            ("Open…", self._animation_open),
            ("Apply Clip", self._animation_apply_clip),
            ("Save", self._animation_save),
        ):
            self.ttk.Button(buttons, text=label, command=command).pack(
                side="left",
                padx=(0, 6),
            )

        tracks = self.ttk.LabelFrame(window, text="Tracks", padding=8)
        tracks.pack(fill="both", expand=True, padx=12, pady=8)
        tree = self.ttk.Treeview(
            tracks,
            columns=("binding", "interpolation", "keys", "range"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("binding", "Binding", 260),
            ("interpolation", "Interpolation", 120),
            ("keys", "Keys", 70),
            ("range", "Range", 160),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width, stretch=column == "binding")
        tree.pack(fill="both", expand=True)
        self._animation_track_tree = tree

        actions = self.ttk.Frame(tracks)
        actions.pack(fill="x", pady=(8, 0))
        for label, command in (
            ("Add Track…", self._animation_add_track),
            ("Remove Track", self._animation_remove_track),
            ("Interpolation…", self._animation_interpolation),
            ("Set Keyframe…", self._animation_set_keyframe),
            ("Remove Keyframe…", self._animation_remove_keyframe),
        ):
            self.ttk.Button(actions, text=label, command=command).pack(
                side="left",
                padx=(0, 6),
            )

        preview = self.ttk.LabelFrame(window, text="Runtime preview", padding=8)
        preview.pack(fill="x", padx=12, pady=(0, 8))
        self.ttk.Entry(
            preview,
            width=10,
            textvariable=self._animation_preview_time_var,
        ).pack(side="left")
        self.ttk.Button(
            preview,
            text="Sample",
            command=self._animation_sample,
        ).pack(side="left", padx=(6, 10))
        self._animation_preview_var = self.tk.StringVar(value="No preview sample")
        self.ttk.Label(preview, textvariable=self._animation_preview_var).pack(
            side="left",
            fill="x",
            expand=True,
        )

        footer = self.ttk.Frame(window, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        self._animation_status_var = self.tk.StringVar()
        self.ttk.Label(footer, textvariable=self._animation_status_var).pack(side="left")
        self.ttk.Button(
            footer,
            text="Close",
            command=self._close_animation_panel,
        ).pack(side="right")
        self._refresh_animation_panel()

    def _selected_animation_binding(self) -> str | None:
        tree = self._animation_track_tree
        if tree is None:
            return None
        selected = tree.selection()
        if not selected:
            return None
        values = tree.item(selected[0], "values")
        return str(values[0]) if values else None

    def _refresh_animation_panel(self) -> None:
        frame = self.animation_controller.frame()
        if self._animation_path_var is not None:
            self._animation_path_var.set(frame.path or "")
            self._animation_name_var.set(frame.name or "")
            self._animation_duration_var.set(
                "" if frame.duration is None else f"{frame.duration:g}"
            )
            self._animation_loop_var.set(frame.loop)
        tree = self._animation_track_tree
        if tree is not None:
            selected = self._selected_animation_binding()
            tree.delete(*tree.get_children())
            for index, row in enumerate(frame.tracks):
                iid = f"animation-track-{index}"
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        row.binding,
                        row.interpolation,
                        row.keyframe_count,
                        f"{row.first_time:g}s → {row.last_time:g}s",
                    ),
                )
                if row.binding == selected:
                    tree.selection_set(iid)
        if self._animation_preview_var is not None:
            if frame.preview_time is None:
                self._animation_preview_var.set("No preview sample")
            else:
                values = ", ".join(
                    f"{key}={value!r}" for key, value in frame.preview_values
                )
                self._animation_preview_var.set(f"t={frame.preview_time:g}s  {values}")
        if self._animation_status_var is not None:
            dirty = " · unsaved" if frame.dirty else ""
            self._animation_status_var.set(self.animation_controller.status + dirty)

    def _animation_new(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "New animation",
            "Clip name:",
            parent=self._animation_window,
        )
        if not name:
            return
        duration = simpledialog.askfloat(
            "New animation",
            "Duration (seconds):",
            initialvalue=1.0,
            minvalue=0.000001,
            parent=self._animation_window,
        )
        if duration is None:
            return
        self._animation_action(
            lambda: self.animation_controller.new_clip(name, duration=duration)
        )

    def _animation_open(self) -> None:
        from tkinter import filedialog

        root = self.animation_controller.tooling.project_root
        path = filedialog.askopenfilename(
            parent=self._animation_window,
            title="Open SwirEngine animation",
            filetypes=(
                ("SwirEngine animation", "*.swiranim.json"),
                ("JSON", "*.json"),
            ),
            initialdir=str(root),
        )
        if not path:
            return
        try:
            project_relative = Path(path).resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            self.messagebox.showerror(
                "SwirEditor — Animation",
                "Animation assets must stay inside the current project.",
                parent=self._animation_window,
            )
            return
        self._animation_action(lambda: self.animation_controller.load(project_relative))

    def _animation_apply_clip(self) -> None:
        def action() -> None:
            frame = self.animation_controller.frame()
            if frame.name is None:
                raise EditorAnimationToolingError("create or open an animation clip first")
            duration = float(self._animation_duration_var.get())
            self.animation_controller.set_duration(duration)
            self.animation_controller.rename_clip(self._animation_name_var.get())
            self.animation_controller.set_loop(bool(self._animation_loop_var.get()))

        self._animation_action(action)

    def _animation_save(self) -> None:
        self._animation_action(self.animation_controller.save)

    def _animation_add_track(self) -> None:
        from tkinter import simpledialog

        binding = simpledialog.askstring(
            "Add track",
            "Binding:",
            parent=self._animation_window,
        )
        if not binding:
            return
        raw = simpledialog.askstring(
            "Add track",
            "Initial value (JSON):",
            initialvalue="0.0",
            parent=self._animation_window,
        )
        if raw is None:
            return
        self._animation_action(
            lambda: self.animation_controller.add_track(
                binding,
                initial_value=parse_animation_value21(raw),
            )
        )

    def _animation_remove_track(self) -> None:
        binding = self._selected_animation_binding()
        if binding is None:
            return
        self._animation_action(lambda: self.animation_controller.remove_track(binding))

    def _animation_interpolation(self) -> None:
        from tkinter import simpledialog

        binding = self._selected_animation_binding()
        if binding is None:
            return
        value = simpledialog.askstring(
            "Interpolation",
            "Mode (linear / step):",
            initialvalue="linear",
            parent=self._animation_window,
        )
        if not value:
            return
        self._animation_action(
            lambda: self.animation_controller.set_interpolation(binding, value)
        )

    def _animation_set_keyframe(self) -> None:
        from tkinter import simpledialog

        binding = self._selected_animation_binding()
        if binding is None:
            return
        time = simpledialog.askfloat(
            "Keyframe",
            "Time (seconds):",
            minvalue=0.0,
            parent=self._animation_window,
        )
        if time is None:
            return
        raw = simpledialog.askstring(
            "Keyframe",
            "Value (JSON):",
            parent=self._animation_window,
        )
        if raw is None:
            return
        self._animation_action(
            lambda: self.animation_controller.set_keyframe(
                binding,
                time,
                parse_animation_value21(raw),
            )
        )

    def _animation_remove_keyframe(self) -> None:
        from tkinter import simpledialog

        binding = self._selected_animation_binding()
        if binding is None:
            return
        time = simpledialog.askfloat(
            "Remove keyframe",
            "Time (seconds):",
            minvalue=0.0,
            parent=self._animation_window,
        )
        if time is None:
            return
        self._animation_action(
            lambda: self.animation_controller.remove_keyframe(binding, time)
        )

    def _animation_sample(self) -> None:
        self._animation_action(
            lambda: self.animation_controller.sample(
                float(self._animation_preview_time_var.get())
            )
        )

    def _animation_action(self, action: Any) -> None:
        try:
            action()
        except (EditorAnimationToolingError, TypeError, ValueError, OSError) as exc:
            self.messagebox.showerror(
                "SwirEditor — Animation",
                str(exc),
                parent=self._animation_window,
            )
            return
        self._refresh_animation_panel()

    def _close_animation_panel(self) -> None:
        if self._animation_window is not None and self._animation_window.winfo_exists():
            self._animation_window.destroy()
        self._animation_window = None
