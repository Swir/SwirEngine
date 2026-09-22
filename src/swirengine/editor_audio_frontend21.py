from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audio import AudioEngine
from .editor_audio_tooling21 import EditorAudioTooling21, EditorAudioToolingError
from .editor_navigation_frontend21 import TkNavigationEditorApp21
from .editor_viewport_frontend21 import EditorProductionViewportController21


@dataclass(frozen=True, slots=True)
class AudioBusRow21:
    name: str
    volume: float
    muted: bool


@dataclass(frozen=True, slots=True)
class AudioCueRow21:
    name: str
    asset: str
    bus: str
    volume: float
    loop: bool
    music: bool
    spatial: bool


@dataclass(frozen=True, slots=True)
class AudioPanelFrame21:
    path: str
    dirty: bool
    buses: tuple[AudioBusRow21, ...]
    cues: tuple[AudioCueRow21, ...]


class EditorAudioPanelController21:
    """Toolkit-neutral creator adapter over runtime-backed audio authoring."""

    def __init__(self, tooling: EditorAudioTooling21) -> None:
        if not isinstance(tooling, EditorAudioTooling21):
            raise TypeError("tooling must be an EditorAudioTooling21")
        self.tooling = tooling
        self._preview_engine: AudioEngine | None = None
        self._status = "Audio tooling ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self) -> AudioPanelFrame21:
        snapshot = self.tooling.snapshot()
        return AudioPanelFrame21(
            path=snapshot.path,
            dirty=snapshot.dirty,
            buses=tuple(AudioBusRow21(bus.name, bus.volume, bus.muted) for bus in snapshot.buses),
            cues=tuple(
                AudioCueRow21(
                    cue.name,
                    cue.asset,
                    cue.bus,
                    cue.volume,
                    cue.loop,
                    cue.music,
                    cue.position is not None,
                )
                for cue in snapshot.cues
            ),
        )

    def create_bus(self, name: str, *, volume: float = 1.0, muted: bool = False) -> AudioPanelFrame21:
        self.tooling.create_bus(name, volume=volume, muted=muted)
        self._status = f"Created audio bus {name}"
        return self.frame()

    def update_bus(self, name: str, **changes: Any) -> AudioPanelFrame21:
        self.tooling.update_bus(name, **changes)
        self._status = f"Updated audio bus {name}"
        return self.frame()

    def remove_bus(self, name: str) -> AudioPanelFrame21:
        self.tooling.remove_bus(name)
        self._status = f"Removed audio bus {name}"
        return self.frame()

    def create_cue(self, name: str, asset: str, **settings: Any) -> AudioPanelFrame21:
        self.tooling.create_cue(name, asset, **settings)
        self._status = f"Created audio cue {name}"
        return self.frame()

    def update_cue(self, name: str, **changes: Any) -> AudioPanelFrame21:
        self.tooling.update_cue(name, **changes)
        self._status = f"Updated audio cue {name}"
        return self.frame()

    def remove_cue(self, name: str) -> AudioPanelFrame21:
        self.stop_preview()
        self.tooling.remove_cue(name)
        self._status = f"Removed audio cue {name}"
        return self.frame()

    def preview(self, name: str) -> AudioPanelFrame21:
        self.stop_preview()
        engine, _handle = self.tooling.preview_cue(name)
        self._preview_engine = engine
        self._status = f"Previewing audio cue {name}"
        return self.frame()

    def stop_preview(self) -> AudioPanelFrame21:
        if self._preview_engine is not None:
            self._preview_engine.shutdown()
            self._preview_engine = None
            self._status = "Stopped audio preview"
        return self.frame()

    def save(self) -> AudioPanelFrame21:
        snapshot = self.tooling.save()
        self._status = f"Saved audio configuration {snapshot.path}"
        return self.frame()

    def reload(self) -> AudioPanelFrame21:
        self.stop_preview()
        self.tooling.load()
        self._status = "Reloaded saved audio configuration"
        return self.frame()

    def close(self) -> None:
        if self._preview_engine is not None:
            self._preview_engine.shutdown()
            self._preview_engine = None


class TkAudioEditorApp21(TkNavigationEditorApp21):
    """Production SwirEditor shell with integrated audio authoring and preview."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        audio: EditorAudioTooling21,
        **kwargs: Any,
    ) -> None:
        self.audio_controller = EditorAudioPanelController21(audio)
        self._audio_window: Any | None = None
        self._audio_buses_tree: Any | None = None
        self._audio_cues_tree: Any | None = None
        self._audio_status_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        audio = self.tk.Menu(menu, tearoff=False)
        audio.add_command(label="Mixer & Cues…", command=self._open_audio_panel)
        menu.add_cascade(label="Audio", menu=audio)

    def _open_audio_panel(self) -> None:
        if self._audio_window is not None and self._audio_window.winfo_exists():
            self._audio_window.deiconify()
            self._audio_window.lift()
            self._audio_window.focus_force()
            return
        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — Audio")
        window.geometry("980x680")
        window.minsize(760, 500)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_audio_panel)
        self._audio_window = window

        notebook = self.ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        self._audio_buses_tree = self._build_audio_tree(
            notebook,
            "Mixer buses",
            (("name", "Name", 220), ("volume", "Volume", 100), ("muted", "Muted", 100)),
        )
        self._audio_cues_tree = self._build_audio_tree(
            notebook,
            "Cues",
            (
                ("name", "Name", 170),
                ("asset", "Asset", 260),
                ("bus", "Bus", 100),
                ("volume", "Volume", 90),
                ("flags", "Mode", 150),
            ),
        )

        actions = self.ttk.Frame(window, padding=(12, 0, 12, 8))
        actions.pack(fill="x")
        for label, command in (
            ("Add Bus…", self._audio_add_bus),
            ("Add Cue…", self._audio_add_cue),
            ("Remove", self._audio_remove_selected),
            ("Preview", self._audio_preview_selected),
            ("Stop", self._audio_stop_preview),
            ("Save", self._audio_save),
            ("Reload", self._audio_reload),
        ):
            self.ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6))

        footer = self.ttk.Frame(window, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        self._audio_status_var = self.tk.StringVar()
        self.ttk.Label(footer, textvariable=self._audio_status_var).pack(side="left")
        self.ttk.Button(footer, text="Close", command=self._close_audio_panel).pack(side="right")
        self._refresh_audio_panel()

    def _build_audio_tree(
        self,
        notebook: Any,
        title: str,
        columns: tuple[tuple[str, str, int], ...],
    ) -> Any:
        frame = self.ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=title)
        keys = tuple(column[0] for column in columns)
        tree = self.ttk.Treeview(frame, columns=keys, show="headings", selectmode="browse")
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key in {"name", "asset"})
        tree.pack(fill="both", expand=True)
        return tree

    def _refresh_audio_panel(self) -> None:
        frame = self.audio_controller.frame()
        self._replace_audio_rows(
            self._audio_buses_tree,
            ((row.name, f"{row.volume:.2f}", "yes" if row.muted else "no") for row in frame.buses),
            "audio-bus",
        )
        self._replace_audio_rows(
            self._audio_cues_tree,
            (
                (
                    row.name,
                    row.asset,
                    row.bus,
                    f"{row.volume:.2f}",
                    "music" if row.music else ("spatial" if row.spatial else ("loop" if row.loop else "sfx")),
                )
                for row in frame.cues
            ),
            "audio-cue",
        )
        if self._audio_status_var is not None:
            dirty = " · unsaved" if frame.dirty else ""
            self._audio_status_var.set(self.audio_controller.status + dirty)

    @staticmethod
    def _replace_audio_rows(tree: Any | None, rows: Any, prefix: str) -> None:
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for index, values in enumerate(rows):
            tree.insert("", "end", iid=f"{prefix}-{index}", values=values)

    def _audio_add_bus(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add audio bus", "Name:", parent=self._audio_window)
        if not name:
            return
        volume = simpledialog.askfloat(
            "Add audio bus", "Volume (0..1):", initialvalue=1.0, minvalue=0.0, maxvalue=1.0,
            parent=self._audio_window,
        )
        if volume is None:
            return
        self._audio_action(lambda: self.audio_controller.create_bus(name, volume=volume))

    def _audio_add_cue(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add audio cue", "Name:", parent=self._audio_window)
        if not name:
            return
        asset = simpledialog.askstring(
            "Add audio cue", "Asset path relative to assets/:", parent=self._audio_window
        )
        if not asset:
            return
        bus = simpledialog.askstring(
            "Add audio cue", "Bus:", initialvalue="sfx", parent=self._audio_window
        )
        if not bus:
            return
        volume = simpledialog.askfloat(
            "Add audio cue", "Volume (0..1):", initialvalue=1.0, minvalue=0.0, maxvalue=1.0,
            parent=self._audio_window,
        )
        if volume is None:
            return
        self._audio_action(lambda: self.audio_controller.create_cue(name, asset, bus=bus, volume=volume))

    def _selected_audio_item(self) -> tuple[str, str] | None:
        for kind, tree in (("bus", self._audio_buses_tree), ("cue", self._audio_cues_tree)):
            if tree is None:
                continue
            selection = tree.selection()
            if selection:
                values = tree.item(selection[0], "values")
                if values:
                    return kind, str(values[0])
        return None

    def _audio_remove_selected(self) -> None:
        selected = self._selected_audio_item()
        if selected is None:
            return
        kind, name = selected
        if not self.messagebox.askyesno(
            "Remove audio item", f"Remove {kind} {name}?", parent=self._audio_window
        ):
            return
        action = self.audio_controller.remove_bus if kind == "bus" else self.audio_controller.remove_cue
        self._audio_action(lambda: action(name))

    def _audio_preview_selected(self) -> None:
        selected = self._selected_audio_item()
        if selected is None or selected[0] != "cue":
            self.messagebox.showinfo(
                "SwirEditor — Audio", "Select an audio cue first.", parent=self._audio_window
            )
            return
        self._audio_action(lambda: self.audio_controller.preview(selected[1]))

    def _audio_stop_preview(self) -> None:
        self._audio_action(self.audio_controller.stop_preview)

    def _audio_save(self) -> None:
        self._audio_action(self.audio_controller.save)

    def _audio_reload(self) -> None:
        self._audio_action(self.audio_controller.reload)

    def _audio_action(self, action: Any) -> None:
        try:
            action()
        except (EditorAudioToolingError, FileNotFoundError, RuntimeError, TypeError, ValueError) as exc:
            self.messagebox.showerror("SwirEditor — Audio", str(exc), parent=self._audio_window)
            return
        self._refresh_audio_panel()

    def _close_audio_panel(self) -> None:
        self.audio_controller.close()
        window, self._audio_window = self._audio_window, None
        self._audio_buses_tree = None
        self._audio_cues_tree = None
        self._audio_status_var = None
        if window is not None and window.winfo_exists():
            window.destroy()
