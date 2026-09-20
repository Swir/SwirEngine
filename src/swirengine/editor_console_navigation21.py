from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .editor_diagnostics import EditorConsoleEntry
from .editor_viewport_frontend21 import (
    EditorProductionViewportController21,
    TkProductionViewportEditorApp21,
)


@dataclass(frozen=True, slots=True)
class EditorSourceLocation:
    """Project-scoped source location exposed by the creator console."""

    path: str
    line: int | None = None
    column: int | None = None

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ValueError("source path cannot be empty")
        if self.line is not None and self.line < 1:
            raise ValueError("source line must be at least 1")
        if self.column is not None and self.column < 1:
            raise ValueError("source column must be at least 1")

    @property
    def display(self) -> str:
        suffix = ""
        if self.line is not None:
            suffix = f":{self.line}"
            if self.column is not None:
                suffix += f":{self.column}"
        return f"{self.path}{suffix}"


def source_location_from_exception(
    project_root: str | Path,
    exc: BaseException,
) -> EditorSourceLocation | None:
    """Return the deepest traceback frame that belongs to the opened project."""

    root = Path(project_root).resolve()
    extracted = traceback.extract_tb(exc.__traceback__)
    for frame in reversed(extracted):
        candidate = Path(frame.filename).resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        column = getattr(frame, "colno", None)
        if isinstance(column, int) and column >= 0:
            column += 1
        else:
            column = None
        return EditorSourceLocation(relative.as_posix(), frame.lineno, column)
    return None


def resolve_project_source(
    project_root: str | Path,
    location: EditorSourceLocation,
) -> Path | None:
    """Resolve a console location while preventing navigation outside the project root."""

    root = Path(project_root).resolve()
    raw = location.path.strip()
    candidate = Path(raw)
    if not candidate.is_absolute():
        normalized = PurePosixPath(raw.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            return None
        candidate = root / normalized
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved if resolved.is_file() else None


def _vscode_target(path: Path, location: EditorSourceLocation) -> str:
    target = str(path)
    if location.line is not None:
        target += f":{location.line}"
        if location.column is not None:
            target += f":{location.column}"
    return target


def open_project_source(
    project_root: str | Path,
    location: EditorSourceLocation,
) -> bool:
    """Open one validated project source location in VS Code or the OS file association."""

    path = resolve_project_source(project_root, location)
    if path is None:
        return False

    code = shutil.which("code")
    try:
        if code is not None:
            subprocess.Popen(  # noqa: S603 - fixed executable path from shutil.which
                [code, "--goto", _vscode_target(path, location)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        if os.name == "nt":
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                return False
            startfile(str(path))
            return True
        opener_name = "open" if sys.platform == "darwin" else "xdg-open"
        opener = shutil.which(opener_name)
        if opener is None:
            return False
        subprocess.Popen(  # noqa: S603 - fixed executable path from shutil.which
            [opener, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return True


class TkConsoleNavigationEditorApp21(TkProductionViewportEditorApp21):
    """Production creator shell with double-click console source navigation."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        project_root: str | Path,
        **kwargs: Any,
    ) -> None:
        self._project_root = Path(project_root).resolve()
        self._console_sequences: list[int] = []
        super().__init__(controller, **kwargs)
        self.console_text.bind("<Double-Button-1>", self._console_open_source)

    def _refresh_console(self, frame: Any) -> None:
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", "end")
        self._console_sequences.clear()
        if frame.console is not None:
            for entry in frame.console.entries:
                location = _entry_location(entry)
                suffix = "" if location is None else f" [{location.display}]"
                self.console_text.insert(
                    "end",
                    f"[{entry.level.upper():8}] {entry.source}: {entry.message}{suffix}\n",
                )
                self._console_sequences.append(entry.sequence)
        self.console_text.configure(state="disabled")

    def _console_open_source(self, event: Any) -> str | None:
        console = self.controller.console
        if console is None:
            return None
        try:
            line_index = int(self.console_text.index(f"@{event.x},{event.y}").split(".", 1)[0]) - 1
        except (TypeError, ValueError):
            return None
        if line_index < 0 or line_index >= len(self._console_sequences):
            return None
        sequence = self._console_sequences[line_index]
        entry = next((item for item in console.entries if item.sequence == sequence), None)
        if entry is None:
            return None
        location = _entry_location(entry)
        if location is None:
            self.status_var.set("Console entry has no source location")
            return "break"
        if open_project_source(self._project_root, location):
            self.status_var.set(f"Opened {location.display}")
        else:
            self.status_var.set(f"Cannot open project source {location.display}")
        return "break"


def _entry_location(entry: EditorConsoleEntry) -> EditorSourceLocation | None:
    if entry.path is None:
        return None
    return EditorSourceLocation(entry.path, entry.line, entry.column)
