from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .editor_build_export_tooling21 import (
    EditorBuildExportTooling21,
    EditorBuildExportToolingError,
)
from .editor_save_profile_frontend21 import TkSaveProfileEditorApp21
from .editor_viewport_frontend21 import EditorProductionViewportController21
from .exporting import (
    ExportResult,
    ExportTarget,
    NativeBuildResult,
    PackagingProfile,
    ProjectExporter,
)


@dataclass(frozen=True, slots=True)
class BuildExportPanelFrame21:
    active_profile: str
    profile_names: tuple[str, ...]
    target: str
    app_name: str
    entrypoint: str
    icon: str | None
    metadata: tuple[tuple[str, str], ...]
    onefile: bool
    console: bool
    output_root: str
    output_dir: str
    planned_file_count: int
    experimental: bool
    native_build_planned: bool
    dirty: bool


@dataclass(frozen=True, slots=True)
class BuildArtifactInspection21:
    output_dir: str
    manifest: str
    file_count: int
    total_bytes: int
    checksums_verified: bool
    missing_files: tuple[str, ...]
    mismatched_files: tuple[str, ...]
    native_spec: str | None
    native_artifacts: tuple[str, ...] = ()


class EditorBuildExportPanelController21:
    """Toolkit-neutral Build/Export Wizard adapter over the shipping exporter."""

    def __init__(self, tooling: EditorBuildExportTooling21) -> None:
        if not isinstance(tooling, EditorBuildExportTooling21):
            raise TypeError("tooling must be an EditorBuildExportTooling21")
        self.tooling = tooling
        self._status = "Build/Export Wizard ready"
        self._last_artifact: BuildArtifactInspection21 | None = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_artifact(self) -> BuildArtifactInspection21 | None:
        return self._last_artifact

    def frame(self) -> BuildExportPanelFrame21:
        config = self.tooling.config
        profile = config.active
        plan = self.tooling.preflight()
        return BuildExportPanelFrame21(
            active_profile=config.active_profile,
            profile_names=tuple(item.name for item in config.profiles),
            target=profile.target.value,
            app_name=profile.effective_app_name,
            entrypoint=profile.entrypoint,
            icon=profile.icon,
            metadata=tuple(sorted(profile.metadata.items())),
            onefile=profile.onefile,
            console=profile.console,
            output_root=config.output_root,
            output_dir=str(plan.output_dir),
            planned_file_count=len(plan.files),
            experimental=plan.experimental,
            native_build_planned=plan.native_build_command is not None,
            dirty=self.tooling.dirty,
        )

    def select_profile(self, name: str) -> BuildExportPanelFrame21:
        self.tooling.select_profile(name)
        self._status = f"Selected export profile {name}"
        return self.frame()

    def set_output_root(self, path: str) -> BuildExportPanelFrame21:
        self.tooling.set_output_root(path)
        self._status = f"Export output root set to {self.tooling.config.output_root}"
        return self.frame()

    def upsert_profile(
        self,
        profile: PackagingProfile,
        *,
        select: bool = True,
    ) -> BuildExportPanelFrame21:
        self.tooling.upsert_profile(profile)
        if select:
            self.tooling.select_profile(profile.name)
        self._status = f"Updated export profile {profile.name}"
        return self.frame()

    def configure_active_profile(
        self,
        *,
        name: str,
        target: ExportTarget,
        entrypoint: str,
        app_name: str,
        icon: str | None,
        onefile: bool,
        console: bool,
        metadata: dict[str, str],
    ) -> BuildExportPanelFrame21:
        """Apply creator-authored shipping fields without bypassing PackagingProfile."""

        current = self.tooling.config.active
        clean_name = name.strip()
        if clean_name != current.name and any(
            profile.name == clean_name for profile in self.tooling.config.profiles
        ):
            raise EditorBuildExportToolingError(
                f"export profile already exists: {clean_name}"
            )
        profile = PackagingProfile(
            name=clean_name,
            target=target,
            entrypoint=entrypoint.strip(),
            app_name=app_name.strip() or None,
            include=current.include,
            exclude=current.exclude,
            icon=(icon.strip() or None) if icon is not None else None,
            onefile=bool(onefile),
            console=bool(console),
            metadata=dict(metadata),
        )
        output_root = self.tooling.project_root / self.tooling.config.output_root
        ProjectExporter(self.tooling.project_root).plan(
            profile,
            output_root / f"{profile.effective_app_name}-{profile.target.value}",
        )
        previous_name = current.name
        self.tooling.upsert_profile(profile)
        self.tooling.select_profile(profile.name)
        if previous_name != profile.name:
            self.tooling.remove_profile(previous_name)
        self._status = f"Configured export profile {profile.name}"
        return self.frame()

    def remove_profile(self, name: str) -> BuildExportPanelFrame21:
        self.tooling.remove_profile(name)
        self._status = f"Removed export profile {name}"
        return self.frame()

    def preflight(self) -> BuildExportPanelFrame21:
        frame = self.frame()
        qualifier = "experimental " if frame.experimental else ""
        self._status = (
            f"Preflight ready: {frame.planned_file_count} files, "
            f"{qualifier}{frame.target} target"
        )
        return frame

    def stage(self, *, clean: bool = True) -> BuildArtifactInspection21:
        result = self.tooling.stage(clean=clean)
        report = self._inspect_export(result)
        self._last_artifact = report
        self._status = (
            f"Staged {report.file_count} files ({report.total_bytes} bytes) "
            f"to {report.output_dir}"
        )
        return report

    def inspect_staged(self) -> BuildArtifactInspection21:
        output_dir = self.tooling.output_dir()
        manifest = output_dir / "swir-export.json"
        if not manifest.is_file():
            raise EditorBuildExportToolingError(
                f"staged export manifest does not exist: {manifest}"
            )
        result = ExportResult(
            output_dir=output_dir,
            manifest=manifest,
            copied_files=(),
            native_build_command=None,
            experimental=False,
            native_spec=(
                output_dir / "swirengine-build.spec"
                if (output_dir / "swirengine-build.spec").is_file()
                else None
            ),
        )
        report = self._inspect_export(result)
        self._last_artifact = report
        self._status = (
            "Staged artifact verification passed"
            if report.checksums_verified
            else "Staged artifact verification found integrity problems"
        )
        return report

    def build_native(
        self,
        *,
        clean: bool = True,
        runner: Any = None,
    ) -> BuildArtifactInspection21:
        result = self.tooling.build_native(clean=clean, runner=runner)
        report = self._inspect_native(result)
        self._last_artifact = report
        self._status = f"Native build produced {len(report.native_artifacts)} artifact(s)"
        return report

    def save(self) -> BuildExportPanelFrame21:
        snapshot = self.tooling.save()
        self._status = f"Saved build/export configuration {snapshot.path}"
        return self.frame()

    def reload(self) -> BuildExportPanelFrame21:
        self.tooling.reload()
        self._status = "Reloaded saved build/export configuration"
        return self.frame()

    @staticmethod
    def _inspect_native(result: NativeBuildResult) -> BuildArtifactInspection21:
        base = EditorBuildExportPanelController21._inspect_export(result.export)
        return BuildArtifactInspection21(
            output_dir=base.output_dir,
            manifest=base.manifest,
            file_count=base.file_count,
            total_bytes=base.total_bytes,
            checksums_verified=base.checksums_verified,
            missing_files=base.missing_files,
            mismatched_files=base.mismatched_files,
            native_spec=base.native_spec,
            native_artifacts=tuple(str(path) for path in result.artifacts),
        )

    @staticmethod
    def _inspect_export(result: ExportResult) -> BuildArtifactInspection21:
        try:
            payload = json.loads(result.manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EditorBuildExportToolingError(
                f"cannot inspect staged export manifest: {exc}"
            ) from exc
        if not isinstance(payload, dict) or payload.get("format") != "swirengine-export":
            raise EditorBuildExportToolingError("unsupported staged export manifest")
        files = payload.get("files")
        checksums = payload.get("sha256")
        if not isinstance(files, list) or not isinstance(checksums, dict):
            raise EditorBuildExportToolingError(
                "staged export manifest must contain files and sha256 maps"
            )

        output_root = result.output_dir.resolve()
        missing: list[str] = []
        mismatched: list[str] = []
        total_bytes = 0
        normalized_files: list[str] = []
        for raw in files:
            if not isinstance(raw, str):
                raise EditorBuildExportToolingError(
                    "staged export manifest contains a non-string file path"
                )
            relative = PurePosixPath(raw)
            if relative.is_absolute() or ".." in relative.parts or raw in {"", "."}:
                raise EditorBuildExportToolingError(
                    f"staged export manifest contains unsafe path: {raw}"
                )
            destination = (output_root / Path(*relative.parts)).resolve(strict=False)
            try:
                destination.relative_to(output_root)
            except ValueError as exc:
                raise EditorBuildExportToolingError(
                    f"staged export manifest path escapes output root: {raw}"
                ) from exc
            normalized_files.append(relative.as_posix())
            if not destination.is_file():
                missing.append(relative.as_posix())
                continue
            total_bytes += destination.stat().st_size
            expected = checksums.get(relative.as_posix())
            if not isinstance(expected, str) or _sha256(destination) != expected:
                mismatched.append(relative.as_posix())

        verified = (
            not missing
            and not mismatched
            and len(normalized_files) == len(checksums)
            and set(normalized_files) == set(checksums)
        )
        return BuildArtifactInspection21(
            output_dir=str(output_root),
            manifest=str(result.manifest.resolve()),
            file_count=len(normalized_files),
            total_bytes=total_bytes,
            checksums_verified=verified,
            missing_files=tuple(missing),
            mismatched_files=tuple(mismatched),
            native_spec=(
                None if result.native_spec is None else str(result.native_spec.resolve())
            ),
        )


class TkBuildExportEditorApp21(TkSaveProfileEditorApp21):
    """SwirEditor shell with creator-facing Build/Export Wizard controls."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        build_export: EditorBuildExportTooling21,
        **kwargs: Any,
    ) -> None:
        self.build_export_controller = EditorBuildExportPanelController21(build_export)
        self._build_export_window: Any | None = None
        self._build_export_vars: dict[str, Any] = {}
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        build_menu = self.tk.Menu(menu, tearoff=False)
        build_menu.add_command(
            label="Build / Export Wizard…",
            command=self._open_build_export_panel,
        )
        menu.add_cascade(label="Build", menu=build_menu)

    def _open_build_export_panel(self) -> None:
        if self._build_export_window is not None and self._build_export_window.winfo_exists():
            self._build_export_window.deiconify()
            self._build_export_window.lift()
            self._build_export_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — Build / Export")
        window.geometry("940x680")
        window.minsize(780, 560)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_build_export_panel)
        self._build_export_window = window

        body = self.ttk.Frame(window, padding=16)
        body.pack(fill="both", expand=True)
        fields = (
            ("active_profile", "Active profile"),
            ("target", "Target"),
            ("app_name", "Application"),
            ("entrypoint", "Entrypoint"),
            ("icon", "Icon"),
            ("metadata", "Metadata"),
            ("onefile", "One-file build"),
            ("console", "Console"),
            ("output_root", "Output root"),
            ("output_dir", "Resolved output"),
            ("planned_file_count", "Planned files"),
            ("native_build_planned", "Native build plan"),
            ("experimental", "Experimental target"),
        )
        for row, (key, label) in enumerate(fields):
            self.ttk.Label(body, text=f"{label}:").grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=4
            )
            variable = self.tk.StringVar()
            self._build_export_vars[key] = variable
            self.ttk.Label(body, textvariable=variable, wraplength=680).grid(
                row=row, column=1, sticky="w", pady=4
            )

        actions = self.ttk.Frame(body)
        actions.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(18, 8))
        action_specs = (
            ("Select Profile…", self._build_export_select_profile),
            ("Edit Profile…", self._build_export_edit_profile),
            ("Output Root…", self._build_export_output_root),
            ("Preflight", self._build_export_preflight),
            ("Stage Export", self._build_export_stage),
            ("Inspect Artifact", self._build_export_inspect),
            ("Build Native", self._build_export_native),
            ("Save Config", self._build_export_save),
        )
        for index, (label, command) in enumerate(action_specs):
            self.ttk.Button(actions, text=label, command=command).grid(
                row=index // 4,
                column=index % 4,
                sticky="ew",
                padx=(0, 6),
                pady=(0, 6),
            )
        for column in range(4):
            actions.columnconfigure(column, weight=1)

        self._build_export_vars["status"] = self.tk.StringVar()
        self.ttk.Label(
            body,
            textvariable=self._build_export_vars["status"],
            wraplength=860,
        ).grid(
            row=len(fields) + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
        )
        self.ttk.Button(body, text="Close", command=self._close_build_export_panel).grid(
            row=len(fields) + 2,
            column=1,
            sticky="e",
            pady=(18, 0),
        )
        body.columnconfigure(1, weight=1)
        self._refresh_build_export_panel()

    def _refresh_build_export_panel(self) -> None:
        frame = self.build_export_controller.frame()
        metadata = ", ".join(f"{key}={value}" for key, value in frame.metadata) or "(none)"
        values = {
            "active_profile": frame.active_profile,
            "target": frame.target,
            "app_name": frame.app_name,
            "entrypoint": frame.entrypoint,
            "icon": frame.icon or "(none)",
            "metadata": metadata,
            "onefile": "yes" if frame.onefile else "no",
            "console": "yes" if frame.console else "no",
            "output_root": frame.output_root,
            "output_dir": frame.output_dir,
            "planned_file_count": str(frame.planned_file_count),
            "native_build_planned": "yes" if frame.native_build_planned else "no",
            "experimental": "yes" if frame.experimental else "no",
        }
        for key, value in values.items():
            variable = self._build_export_vars.get(key)
            if variable is not None:
                variable.set(value)
        status = self._build_export_vars.get("status")
        if status is not None:
            dirty = " · unsaved" if frame.dirty else ""
            artifact = self.build_export_controller.last_artifact
            artifact_text = ""
            if artifact is not None:
                integrity = "verified" if artifact.checksums_verified else "FAILED"
                artifact_text = (
                    f" · artifact {artifact.file_count} files / "
                    f"{artifact.total_bytes} bytes / integrity {integrity}"
                )
            status.set(self.build_export_controller.status + dirty + artifact_text)

    def _build_export_select_profile(self) -> None:
        from tkinter import simpledialog

        frame = self.build_export_controller.frame()
        name = simpledialog.askstring(
            "Build / Export profile",
            "Profile name:\n" + ", ".join(frame.profile_names),
            initialvalue=frame.active_profile,
            parent=self._build_export_window,
        )
        if name is None:
            return
        self._build_export_action(lambda: self.build_export_controller.select_profile(name))

    def _build_export_edit_profile(self) -> None:
        from tkinter import simpledialog

        current = self.build_export_controller.tooling.config.active
        name = simpledialog.askstring(
            "Build / Export profile",
            "Profile name:",
            initialvalue=current.name,
            parent=self._build_export_window,
        )
        if name is None:
            return
        target_text = simpledialog.askstring(
            "Build / Export profile",
            "Target (windows/linux/macos/android/web):",
            initialvalue=current.target.value,
            parent=self._build_export_window,
        )
        if target_text is None:
            return
        entrypoint = simpledialog.askstring(
            "Build / Export profile",
            "Project-relative entrypoint:",
            initialvalue=current.entrypoint,
            parent=self._build_export_window,
        )
        if entrypoint is None:
            return
        app_name = simpledialog.askstring(
            "Build / Export profile",
            "Application name:",
            initialvalue=current.effective_app_name,
            parent=self._build_export_window,
        )
        if app_name is None:
            return
        icon = simpledialog.askstring(
            "Build / Export profile",
            "Project-relative icon path (blank = none):",
            initialvalue=current.icon or "",
            parent=self._build_export_window,
        )
        if icon is None:
            return
        metadata_text = simpledialog.askstring(
            "Build / Export profile",
            "Metadata JSON object (string values):",
            initialvalue=json.dumps(current.metadata, ensure_ascii=False, sort_keys=True),
            parent=self._build_export_window,
        )
        if metadata_text is None:
            return
        onefile = self.messagebox.askyesnocancel(
            "Build / Export profile",
            "Build a one-file executable?\n"
            f"Current: {'yes' if current.onefile else 'no'}",
            parent=self._build_export_window,
        )
        if onefile is None:
            return
        console = self.messagebox.askyesnocancel(
            "Build / Export profile",
            "Keep a console window for the native build?\n"
            f"Current: {'yes' if current.console else 'no'}",
            parent=self._build_export_window,
        )
        if console is None:
            return
        try:
            target = ExportTarget(target_text.strip().lower())
            metadata = _parse_metadata_text(metadata_text)
        except (EditorBuildExportToolingError, ValueError) as exc:
            self.messagebox.showerror(
                "SwirEditor — Build / Export",
                str(exc),
                parent=self._build_export_window,
            )
            return
        self._build_export_action(
            lambda: self.build_export_controller.configure_active_profile(
                name=name,
                target=target,
                entrypoint=entrypoint,
                app_name=app_name,
                icon=icon,
                onefile=onefile,
                console=console,
                metadata=metadata,
            )
        )

    def _build_export_output_root(self) -> None:
        from tkinter import simpledialog

        output_root = simpledialog.askstring(
            "Build / Export output",
            "Project-relative output root:",
            initialvalue=self.build_export_controller.tooling.config.output_root,
            parent=self._build_export_window,
        )
        if output_root is None:
            return
        self._build_export_action(
            lambda: self.build_export_controller.set_output_root(output_root)
        )

    def _build_export_preflight(self) -> None:
        self._build_export_action(self.build_export_controller.preflight)

    def _build_export_stage(self) -> None:
        self._build_export_action(self.build_export_controller.stage)

    def _build_export_inspect(self) -> None:
        self._build_export_action(self.build_export_controller.inspect_staged)

    def _build_export_native(self) -> None:
        self._build_export_action(self.build_export_controller.build_native)

    def _build_export_save(self) -> None:
        self._build_export_action(self.build_export_controller.save)

    def _build_export_action(self, operation: Any) -> None:
        try:
            operation()
        except (
            EditorBuildExportToolingError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.messagebox.showerror(
                "SwirEditor — Build / Export",
                str(exc),
                parent=self._build_export_window,
            )
        self._refresh_build_export_panel()

    def _close_build_export_panel(self) -> None:
        if self._build_export_window is not None:
            self._build_export_window.destroy()
        self._build_export_window = None
        self._build_export_vars.clear()


def _parse_metadata_text(text: str) -> dict[str, str]:
    value = text.strip()
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise EditorBuildExportToolingError(
            f"metadata must be valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise EditorBuildExportToolingError("metadata must be a JSON object")
    metadata: dict[str, str] = {}
    for key, item in payload.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise EditorBuildExportToolingError(
                "metadata keys and values must be strings"
            )
        metadata[key] = item
    return metadata


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
