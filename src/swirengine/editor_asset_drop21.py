from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .editor_asset_frontend21 import TkAssetPipelineEditorApp21


@dataclass(frozen=True, slots=True)
class NativeAssetDropStatus21:
    """Runtime status for SwirEditor's optional native OS file-drop bridge."""

    enabled: bool
    action: str
    message: str
    targets: int = 0


def split_external_drop_paths21(
    data: object,
    splitlist: Callable[[str], Any],
) -> tuple[str, ...]:
    """Decode a TkDnD file-list payload without corrupting paths that contain spaces.

    TkDnD uses Tcl list syntax for ``DND_FILES`` payloads. The active Tk interpreter
    is therefore the authoritative parser. A conservative single-item fallback keeps
    malformed third-party events from crashing the editor while preserving the raw
    path for normal import validation.
    """

    if not callable(splitlist):
        raise TypeError("splitlist must be callable")
    raw = "" if data is None else str(data).strip()
    if not raw:
        return ()

    try:
        values = splitlist(raw)
    except Exception:  # noqa: BLE001 - Tcl/Tk is a third-party event boundary.
        values = (raw,)
    if isinstance(values, str):
        values = (values,)

    paths: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value).strip()
        if candidate.startswith("{") and candidate.endswith("}") and len(candidate) >= 2:
            candidate = candidate[1:-1]
        if not candidate:
            continue
        candidate = str(Path(candidate).expanduser())
        identity = os.path.normcase(os.path.normpath(candidate))
        if identity in seen:
            continue
        seen.add(identity)
        paths.append(candidate)
    return tuple(paths)


def _tkinterdnd_backend21() -> tuple[Callable[[Any], Any], str, str]:
    """Load the pinned TkDnD bridge lazily so headless engine imports stay Tk-free."""

    from tkinterdnd2 import COPY, DND_FILES, TkinterDnD

    require = getattr(TkinterDnD, "_require", None)
    if not callable(require):
        raise TypeError("tkinterdnd2 does not expose a callable TkDnD loader")
    return require, str(DND_FILES), str(COPY)


def install_native_asset_drop21(
    root: Any,
    targets: Iterable[Any],
    callback: Callable[[Any], Any],
    *,
    loader: Callable[[], tuple[Callable[[Any], Any], str, str]] | None = None,
) -> NativeAssetDropStatus21:
    """Enable native file/folder drops on existing Tk widgets.

    ``tkinterdnd2`` installs its widget methods when imported. SwirEditor already owns
    a regular ``tk.Tk`` root, so this adapter loads the packaged TkDnD extension into
    that interpreter and registers only the Assets-tab targets. Failure is contained:
    file/folder picker buttons remain fully operational.
    """

    if not callable(callback):
        raise TypeError("callback must be callable")
    backend_loader = _tkinterdnd_backend21 if loader is None else loader
    try:
        require, dnd_files, copy_action = backend_loader()
        require(root)
    except (ImportError, RuntimeError, AttributeError, TypeError) as exc:
        return NativeAssetDropStatus21(
            False,
            "copy",
            f"Native drag & drop unavailable ({exc}); use Import Files/Folder.",
        )

    registered = 0
    failures: list[str] = []
    for target in tuple(targets):
        register = getattr(target, "drop_target_register", None)
        bind = getattr(target, "dnd_bind", None)
        if not callable(register) or not callable(bind):
            failures.append("target lacks TkDnD methods")
            continue
        try:
            register(dnd_files)
            bind("<<Drop>>", callback)
        except Exception as exc:  # noqa: BLE001 - Tcl/Tk extension failures must not kill editor.
            failures.append(str(exc) or type(exc).__name__)
            continue
        registered += 1

    if registered == 0:
        detail = failures[0] if failures else "no compatible drop target"
        return NativeAssetDropStatus21(
            False,
            copy_action or "copy",
            f"Native drag & drop unavailable ({detail}); use Import Files/Folder.",
        )
    return NativeAssetDropStatus21(
        True,
        copy_action or "copy",
        f"Native file/folder drag & drop ready on {registered} Assets target(s).",
        registered,
    )


class TkNativeDropAssetPipelineEditorApp21(TkAssetPipelineEditorApp21):
    """SwirEditor Assets workflow with native operating-system file/folder drops."""

    def __init__(self, controller: Any, asset_workflow: Any, **kwargs: Any) -> None:
        super().__init__(controller, asset_workflow, **kwargs)
        self.native_asset_drop = install_native_asset_drop21(
            self.root,
            (self.assets_tree, self.assets_tab),
            self._asset_external_drop,
        )
        self.asset_pipeline_var.set(self.native_asset_drop.message)

    def _asset_external_drop(self, event: Any) -> str:
        splitlist = getattr(getattr(self.root, "tk", None), "splitlist", None)
        if not callable(splitlist):
            self.asset_pipeline_var.set(
                "Native drag & drop payload parser unavailable; use Import Files/Folder."
            )
            return self.native_asset_drop.action
        paths = split_external_drop_paths21(getattr(event, "data", ""), splitlist)
        if not paths:
            self.asset_pipeline_var.set("Drop contained no files or folders.")
            return self.native_asset_drop.action
        self._run_asset_import(paths)
        return self.native_asset_drop.action
