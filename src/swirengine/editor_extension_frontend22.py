"""Declarative Tk host for the restricted SwirEditor 2.2 extension SDK."""

from __future__ import annotations

from typing import Any

from .editor_extension_sdk22 import (
    MAX_EDITOR_EXTENSIONS_22,
    MAX_EXTENSION_ACTIONS_22,
    MAX_EXTENSION_ACTIONS_PER_PANEL_22,
    MAX_EXTENSION_PANELS_22,
    MAX_EXTENSION_ROWS_PER_PANEL_22,
    EditorExtensionActionResult22,
    EditorExtensionPanel22,
    EditorExtensionRegistry22,
    EditorExtensionRegistrySnapshot22,
    EditorExtensionView22,
)
from .editor_ui_designer_frontend22 import TkUIDesignerEditorApp22


class TkEditorExtensionHostApp22(TkUIDesignerEditorApp22):
    """Render bounded extension declarations without exposing editor internals.

    The host owns ``editor_extensions`` for its lifetime and shuts the registry down when the
    editor closes. Extensions receive only their SDK context during explicit registration;
    this frontend invokes actions by stable IDs and never passes the app, root, session, scene,
    renderer, or any Tk widget to an extension callback.
    """

    def __init__(
        self,
        controller: Any,
        *,
        editor_extensions: EditorExtensionRegistry22,
        **kwargs: Any,
    ) -> None:
        if not isinstance(editor_extensions, EditorExtensionRegistry22):
            raise TypeError("editor_extensions must be an EditorExtensionRegistry22")
        self.editor_extension_registry = editor_extensions
        self._editor_extension_window: Any | None = None
        self._editor_extension_after: Any | None = None
        self._editor_extension_notebook: Any | None = None
        self._editor_extension_status: Any | None = None
        self._editor_extension_snapshot: EditorExtensionRegistrySnapshot22 | None = None
        self._editor_extension_action_buttons: dict[tuple[str, str], Any] = {}
        self._editor_extension_row_values: dict[tuple[str, str, str], Any] = {}
        self._editor_extensions_shutdown = False
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        menu.add_command(
            label="Editor Extensions...",
            command=self._open_editor_extensions,
        )

    def _open_editor_extensions(self) -> None:
        window = self._editor_extension_window
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            return
        window = self.tk.Toplevel(self.root)
        self._editor_extension_window = window
        window.title("SwirEditor 2.2 - Extensions")
        window.geometry("900x620")
        window.minsize(720, 480)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_editor_extensions)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        notebook = self.ttk.Notebook(window)
        self._editor_extension_notebook = notebook
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        self._editor_extension_status = self.tk.StringVar(value="Extensions ready")
        self.ttk.Label(
            window,
            textvariable=self._editor_extension_status,
            anchor="w",
            padding=(10, 6),
        ).grid(row=1, column=0, sticky="ew")
        self._refresh_editor_extensions()
        self._schedule_editor_extensions()

    def _schedule_editor_extensions(self) -> None:
        if self._editor_extension_after is None and self._editor_extension_window is not None:
            self._editor_extension_after = self.root.after(
                250,
                self._editor_extension_tick,
            )

    def _editor_extension_tick(self) -> None:
        self._editor_extension_after = None
        if self._editor_extension_window is None:
            return
        self._refresh_editor_extensions()
        self._schedule_editor_extensions()

    def _refresh_editor_extensions(self) -> None:
        if self._editor_extension_notebook is None:
            return
        try:
            snapshot = self._bounded_editor_extension_snapshot()
        except Exception:  # noqa: BLE001 - no provider detail may escape into the Tk loop.
            self._report_editor_extension_error()
            return
        if snapshot == self._editor_extension_snapshot:
            return
        self._editor_extension_snapshot = snapshot
        self._render_editor_extension_snapshot(snapshot)
        if self._editor_extension_status is not None:
            count = len(snapshot.extensions)
            suffix = "extension" if count == 1 else "extensions"
            self._editor_extension_status.set(f"{count} {suffix} loaded")

    def _bounded_editor_extension_snapshot(self) -> EditorExtensionRegistrySnapshot22:
        snapshot = self.editor_extension_registry.snapshot()
        if not isinstance(snapshot, EditorExtensionRegistrySnapshot22):
            raise TypeError("invalid extension registry snapshot")
        if len(snapshot.extensions) > MAX_EDITOR_EXTENSIONS_22:
            raise ValueError("extension snapshot exceeds the host limit")
        ordered_views: list[EditorExtensionView22] = []
        for view in snapshot.extensions:
            if not isinstance(view, EditorExtensionView22):
                raise TypeError("invalid extension view")
            if len(view.panels) > MAX_EXTENSION_PANELS_22:
                raise ValueError("extension view exceeds the panel limit")
            ordered_panels = tuple(
                sorted(view.panels, key=lambda panel: _stable_key(panel.panel_id))
            )
            action_count = 0
            for panel in ordered_panels:
                self._validate_editor_extension_panel(panel)
                action_count += len(panel.actions)
            if action_count > MAX_EXTENSION_ACTIONS_22:
                raise ValueError("extension view exceeds the action limit")
            ordered_views.append(EditorExtensionView22(view.manifest, ordered_panels))
        ordered_views.sort(key=lambda view: _stable_key(view.manifest.extension_id))
        return EditorExtensionRegistrySnapshot22(tuple(ordered_views))

    @staticmethod
    def _validate_editor_extension_panel(panel: object) -> None:
        if not isinstance(panel, EditorExtensionPanel22):
            raise TypeError("invalid extension panel")
        if len(panel.rows) > MAX_EXTENSION_ROWS_PER_PANEL_22:
            raise ValueError("extension panel exceeds the row limit")
        if len(panel.actions) > MAX_EXTENSION_ACTIONS_PER_PANEL_22:
            raise ValueError("extension panel exceeds the action limit")

    def _render_editor_extension_snapshot(
        self,
        snapshot: EditorExtensionRegistrySnapshot22,
    ) -> None:
        notebook = self._editor_extension_notebook
        if notebook is None:
            return
        for tab_id in tuple(notebook.tabs()):
            child = notebook.nametowidget(tab_id)
            notebook.forget(tab_id)
            child.destroy()
        self._editor_extension_action_buttons.clear()
        self._editor_extension_row_values.clear()

        if not snapshot.extensions:
            empty = self.ttk.Frame(notebook, padding=16)
            self.ttk.Label(
                empty,
                text="No editor extensions are registered.",
                anchor="center",
            ).grid(row=0, column=0, sticky="nsew")
            empty.columnconfigure(0, weight=1)
            empty.rowconfigure(0, weight=1)
            notebook.add(empty, text="Extensions")
            return

        for view in snapshot.extensions:
            extension_frame = self.ttk.Frame(notebook, padding=8)
            extension_frame.columnconfigure(0, weight=1)
            extension_frame.rowconfigure(1, weight=1)
            self.ttk.Label(
                extension_frame,
                text=f"{view.manifest.name} {view.manifest.version}",
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", pady=(0, 6))
            panel_notebook = self.ttk.Notebook(extension_frame)
            panel_notebook.grid(row=1, column=0, sticky="nsew")
            notebook.add(extension_frame, text=view.manifest.name)
            if not view.panels:
                empty_panel = self.ttk.Frame(panel_notebook, padding=16)
                self.ttk.Label(
                    empty_panel,
                    text="This extension has no published panels.",
                ).grid(row=0, column=0, sticky="w")
                panel_notebook.add(empty_panel, text="Overview")
                continue
            for panel in view.panels:
                self._render_editor_extension_panel(
                    panel_notebook,
                    view.manifest.extension_id,
                    panel,
                )

    def _render_editor_extension_panel(
        self,
        notebook: Any,
        extension_id: str,
        panel: EditorExtensionPanel22,
    ) -> None:
        frame = self.ttk.Frame(notebook, padding=12)
        frame.columnconfigure(1, weight=1)
        row_index = 0
        if panel.description:
            self.ttk.Label(
                frame,
                text=panel.description,
                anchor="w",
                wraplength=700,
            ).grid(row=row_index, column=0, columnspan=2, sticky="ew", pady=(0, 8))
            row_index += 1
        for row in panel.rows:
            self.ttk.Label(frame, text=row.label, anchor="w").grid(
                row=row_index,
                column=0,
                sticky="nw",
                padx=(0, 12),
                pady=2,
            )
            value = self.ttk.Label(
                frame,
                text=row.value,
                anchor="w",
                wraplength=560,
            )
            value.grid(row=row_index, column=1, sticky="ew", pady=2)
            self._editor_extension_row_values[
                (
                    extension_id.casefold(),
                    panel.panel_id.casefold(),
                    row.row_id.casefold(),
                )
            ] = value
            row_index += 1
        if panel.actions:
            actions = self.ttk.Frame(frame)
            actions.grid(
                row=row_index,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(10, 0),
            )
            for action in panel.actions:
                button = self.ttk.Button(
                    actions,
                    text=action.label,
                    state="normal" if action.enabled else "disabled",
                    command=lambda extension_id=extension_id, action_id=action.action_id: (
                        self._invoke_editor_extension_action(extension_id, action_id)
                    ),
                )
                button.pack(side="left", padx=(0, 6))
                self._editor_extension_action_buttons[
                    (extension_id.casefold(), action.action_id.casefold())
                ] = button
        notebook.add(frame, text=panel.title)

    def _invoke_editor_extension_action(
        self,
        extension_id: str,
        action_id: str,
    ) -> None:
        try:
            result = self.editor_extension_registry.invoke_action(
                extension_id,
                action_id,
            )
            if not isinstance(result, EditorExtensionActionResult22):
                raise TypeError("invalid extension action result")
        except Exception:  # noqa: BLE001 - action providers must not leak details to Tk.
            self._report_editor_extension_error()
            return
        if not result.ok:
            self.controller.console.write(
                result.message,
                level="error",
                source="editor-extensions",
            )
        self._editor_extension_snapshot = None
        self._refresh_editor_extensions()
        if self._editor_extension_status is not None:
            self._editor_extension_status.set(result.message)

    def _report_editor_extension_error(self) -> None:
        message = "Editor extension operation failed."
        if self._editor_extension_status is not None:
            self._editor_extension_status.set(message)
        self.controller.console.write(
            message,
            level="error",
            source="editor-extensions",
        )

    def _close_editor_extensions(self) -> None:
        if self._editor_extension_after is not None:
            try:
                self.root.after_cancel(self._editor_extension_after)
            except Exception:  # noqa: BLE001, S110 - stale Tk state must not block cleanup.
                pass
            self._editor_extension_after = None
        if self._editor_extension_window is not None:
            try:
                self._editor_extension_window.destroy()
            except Exception:  # noqa: BLE001, S110 - stale Tk state must not block cleanup.
                pass
        self._editor_extension_window = None
        self._editor_extension_notebook = None
        self._editor_extension_status = None
        self._editor_extension_snapshot = None
        self._editor_extension_action_buttons.clear()
        self._editor_extension_row_values.clear()

    def close(self) -> None:
        try:
            try:
                self._close_editor_extensions()
            except Exception:  # noqa: BLE001 - registry and base cleanup must still run.
                try:
                    self._report_editor_extension_error()
                except Exception:  # noqa: BLE001, S110 - reporting must not block cleanup.
                    pass
            try:
                if not self._editor_extensions_shutdown:
                    self._editor_extensions_shutdown = True
                    self.editor_extension_registry.shutdown()
            except Exception:  # noqa: BLE001 - base editor cleanup must still run.
                try:
                    self._report_editor_extension_error()
                except Exception:  # noqa: BLE001, S110 - reporting must not block cleanup.
                    pass
        finally:
            super().close()


def _stable_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


__all__ = ["TkEditorExtensionHostApp22"]
