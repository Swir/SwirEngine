from __future__ import annotations

from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import Any

from .editor_save_profile_tooling21 import (
    EditorSaveProfileTooling21,
    EditorSaveProfileToolingError,
)
from .editor_ui_frontend21 import TkUIHudEditorApp21
from .editor_viewport_frontend21 import EditorProductionViewportController21


@dataclass(frozen=True, slots=True)
class SaveProfilePanelFrame21:
    path: str
    app_id: str
    default_profile: str
    version: int
    autosave_keep: int
    autosave_interval_seconds: float
    max_manual_slots: int
    max_snapshot_bytes: int
    dirty: bool


class EditorSaveProfilePanelController21:
    """Toolkit-neutral creator adapter over the production save/profile runtime."""

    def __init__(self, tooling: EditorSaveProfileTooling21) -> None:
        if not isinstance(tooling, EditorSaveProfileTooling21):
            raise TypeError("tooling must be an EditorSaveProfileTooling21")
        self.tooling = tooling
        self._status = "Save/Profile tooling ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self) -> SaveProfilePanelFrame21:
        snapshot = self.tooling.snapshot()
        config = snapshot.config
        return SaveProfilePanelFrame21(
            path=snapshot.path,
            app_id=config.app_id,
            default_profile=config.default_profile,
            version=config.version,
            autosave_keep=config.policy.autosave_keep,
            autosave_interval_seconds=config.policy.autosave_interval_seconds,
            max_manual_slots=config.policy.max_manual_slots,
            max_snapshot_bytes=config.policy.max_snapshot_bytes,
            dirty=snapshot.dirty,
        )

    def update_identity(
        self,
        *,
        app_id: str | None = None,
        default_profile: str | None = None,
        version: int | None = None,
    ) -> SaveProfilePanelFrame21:
        self.tooling.update_identity(
            app_id=app_id,
            default_profile=default_profile,
            version=version,
        )
        self._status = "Updated save/profile identity"
        return self.frame()

    def update_policy(self, **changes: Any) -> SaveProfilePanelFrame21:
        self.tooling.update_policy(**changes)
        self._status = "Updated save/profile policy"
        return self.frame()

    def validate_runtime(self) -> SaveProfilePanelFrame21:
        with TemporaryDirectory(prefix="swir-save-profile-preview-") as root:
            self.tooling.validate_runtime(root)
        self._status = "Runtime save/load preview valid"
        return self.frame()

    def save(self) -> SaveProfilePanelFrame21:
        snapshot = self.tooling.save()
        self._status = f"Saved save/profile configuration {snapshot.path}"
        return self.frame()

    def reload(self) -> SaveProfilePanelFrame21:
        self.tooling.reload()
        self._status = "Reloaded saved save/profile configuration"
        return self.frame()


class TkSaveProfileEditorApp21(TkUIHudEditorApp21):
    """SwirEditor shell with production Save/Profile creator authoring."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        save_profile: EditorSaveProfileTooling21,
        **kwargs: Any,
    ) -> None:
        self.save_profile_controller = EditorSaveProfilePanelController21(save_profile)
        self._save_profile_window: Any | None = None
        self._save_profile_vars: dict[str, Any] = {}
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        save_menu = self.tk.Menu(menu, tearoff=False)
        save_menu.add_command(
            label="Save/Profile Designer…",
            command=self._open_save_profile_panel,
        )
        menu.add_cascade(label="Save / Profiles", menu=save_menu)

    def _open_save_profile_panel(self) -> None:
        if self._save_profile_window is not None and self._save_profile_window.winfo_exists():
            self._save_profile_window.deiconify()
            self._save_profile_window.lift()
            self._save_profile_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — Save / Profiles")
        window.geometry("720x470")
        window.minsize(620, 420)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_save_profile_panel)
        self._save_profile_window = window

        body = self.ttk.Frame(window, padding=16)
        body.pack(fill="both", expand=True)
        fields = (
            ("app_id", "Application ID"),
            ("default_profile", "Default profile"),
            ("version", "Save schema version"),
            ("autosave_keep", "Autosaves kept"),
            ("autosave_interval_seconds", "Autosave interval (s)"),
            ("max_manual_slots", "Manual slot limit"),
            ("max_snapshot_bytes", "Max snapshot bytes"),
        )
        for row, (key, label) in enumerate(fields):
            self.ttk.Label(body, text=f"{label}:").grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=5
            )
            variable = self.tk.StringVar()
            self._save_profile_vars[key] = variable
            self.ttk.Label(body, textvariable=variable).grid(
                row=row, column=1, sticky="w", pady=5
            )

        actions = self.ttk.Frame(body)
        actions.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(18, 8))
        for label, command in (
            ("Edit Identity…", self._save_profile_edit_identity),
            ("Edit Policy…", self._save_profile_edit_policy),
            ("Validate Runtime", self._save_profile_validate),
            ("Save", self._save_profile_save),
            ("Reload", self._save_profile_reload),
        ):
            self.ttk.Button(actions, text=label, command=command).pack(
                side="left", padx=(0, 6)
            )

        self._save_profile_vars["status"] = self.tk.StringVar()
        self.ttk.Label(body, textvariable=self._save_profile_vars["status"]).grid(
            row=len(fields) + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
        )
        self.ttk.Button(body, text="Close", command=self._close_save_profile_panel).grid(
            row=len(fields) + 2,
            column=1,
            sticky="e",
            pady=(18, 0),
        )
        self._refresh_save_profile_panel()

    def _refresh_save_profile_panel(self) -> None:
        frame = self.save_profile_controller.frame()
        values = {
            "app_id": frame.app_id,
            "default_profile": frame.default_profile,
            "version": str(frame.version),
            "autosave_keep": str(frame.autosave_keep),
            "autosave_interval_seconds": f"{frame.autosave_interval_seconds:g}",
            "max_manual_slots": str(frame.max_manual_slots),
            "max_snapshot_bytes": str(frame.max_snapshot_bytes),
        }
        for key, value in values.items():
            variable = self._save_profile_vars.get(key)
            if variable is not None:
                variable.set(value)
        status = self._save_profile_vars.get("status")
        if status is not None:
            dirty = " · unsaved" if frame.dirty else ""
            status.set(self.save_profile_controller.status + dirty)

    def _save_profile_edit_identity(self) -> None:
        from tkinter import simpledialog

        frame = self.save_profile_controller.frame()
        app_id = simpledialog.askstring(
            "Save/Profile identity",
            "Application ID:",
            initialvalue=frame.app_id,
            parent=self._save_profile_window,
        )
        if app_id is None:
            return
        profile = simpledialog.askstring(
            "Save/Profile identity",
            "Default profile:",
            initialvalue=frame.default_profile,
            parent=self._save_profile_window,
        )
        if profile is None:
            return
        version = simpledialog.askinteger(
            "Save/Profile identity",
            "Save schema version:",
            initialvalue=frame.version,
            minvalue=1,
            parent=self._save_profile_window,
        )
        if version is None:
            return
        self._save_profile_action(
            lambda: self.save_profile_controller.update_identity(
                app_id=app_id,
                default_profile=profile,
                version=version,
            )
        )

    def _save_profile_edit_policy(self) -> None:
        from tkinter import simpledialog

        frame = self.save_profile_controller.frame()
        keep = simpledialog.askinteger(
            "Save/Profile policy",
            "Autosaves kept (1-16):",
            initialvalue=frame.autosave_keep,
            minvalue=1,
            maxvalue=16,
            parent=self._save_profile_window,
        )
        if keep is None:
            return
        interval = simpledialog.askfloat(
            "Save/Profile policy",
            "Autosave interval seconds:",
            initialvalue=frame.autosave_interval_seconds,
            minvalue=0.0,
            maxvalue=86400.0,
            parent=self._save_profile_window,
        )
        if interval is None:
            return
        slots = simpledialog.askinteger(
            "Save/Profile policy",
            "Maximum manual slots (1-64):",
            initialvalue=frame.max_manual_slots,
            minvalue=1,
            maxvalue=64,
            parent=self._save_profile_window,
        )
        if slots is None:
            return
        self._save_profile_action(
            lambda: self.save_profile_controller.update_policy(
                autosave_keep=keep,
                autosave_interval_seconds=interval,
                max_manual_slots=slots,
            )
        )

    def _save_profile_validate(self) -> None:
        self._save_profile_action(self.save_profile_controller.validate_runtime)

    def _save_profile_save(self) -> None:
        self._save_profile_action(self.save_profile_controller.save)

    def _save_profile_reload(self) -> None:
        self._save_profile_action(self.save_profile_controller.reload)

    def _save_profile_action(self, operation: Any) -> None:
        try:
            operation()
        except (
            EditorSaveProfileToolingError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.messagebox.showerror(
                "SwirEditor — Save/Profile",
                str(exc),
                parent=self._save_profile_window,
            )
        self._refresh_save_profile_panel()

    def _close_save_profile_panel(self) -> None:
        if self._save_profile_window is not None:
            self._save_profile_window.destroy()
        self._save_profile_window = None
        self._save_profile_vars.clear()
