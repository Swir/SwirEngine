from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .asset_pipeline import AssetPipeline
from .assets import AssetManager
from .editor_asset_pipeline21 import (
    EditorAssetDependencyView,
    EditorAssetImportTicket,
    EditorAssetIssue,
    EditorAssetIssueSeverity,
    EditorAssetPipeline21,
    EditorAssetPipelineFrame,
    EditorAssetPreview,
)
from .editor_assets import EditorAssetBrowser
from .editor_viewport_frontend21 import TkProductionViewportEditorApp21

_EDITOR_SOURCE_SUFFIXES = (
    ".bmp",
    ".comp",
    ".csv",
    ".dae",
    ".fbx",
    ".flac",
    ".frag",
    ".geom",
    ".gif",
    ".glb",
    ".glsl",
    ".gltf",
    ".hdr",
    ".jpeg",
    ".jpg",
    ".json",
    ".m4a",
    ".md",
    ".mp3",
    ".obj",
    ".ogg",
    ".otf",
    ".png",
    ".py",
    ".tga",
    ".toml",
    ".ttf",
    ".txt",
    ".vert",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".yaml",
    ".yml",
)


def _source_metadata(path: Path) -> dict[str, object]:
    """Build deterministic, bounded-memory metadata on an AssetPipeline worker."""

    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return {
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def create_editor_asset_pipeline21(
    manager: AssetManager,
    *,
    max_workers: int = 2,
) -> EditorAssetPipeline21:
    """Create the default SwirEditor 2.1 import pipeline on the existing runtime scheduler.

    The default processor deliberately performs only safe source metadata work. Format-specific
    importers can replace or extend it through the same runtime :class:`AssetPipeline` API without
    introducing another editor-only job system.
    """

    if not isinstance(manager, AssetManager):
        raise TypeError("manager must be an AssetManager")
    pipeline = AssetPipeline(manager, max_workers=max_workers)
    pipeline.register_processor(
        "editor-source-metadata",
        suffixes=_EDITOR_SOURCE_SUFFIXES,
        loader=_source_metadata,
    )
    return EditorAssetPipeline21(manager, pipeline)


@dataclass(frozen=True, slots=True)
class EditorAssetWorkflowFrame21:
    """One immutable Assets-tab view model."""

    pipeline: EditorAssetPipelineFrame
    selected_path: str | None
    preview: EditorAssetPreview | None
    dependencies: EditorAssetDependencyView | None
    issues: tuple[EditorAssetIssue, ...]
    message: str = ""

    @property
    def healthy(self) -> bool:
        return not any(issue.blocking for issue in self.issues)


class EditorAssetWorkflow21:
    """Compose browser, import pipeline and creator-facing asset details for SwirEditor."""

    def __init__(
        self,
        backend: EditorAssetPipeline21,
        browser: EditorAssetBrowser,
    ) -> None:
        if not isinstance(backend, EditorAssetPipeline21):
            raise TypeError("backend must be an EditorAssetPipeline21")
        if not isinstance(browser, EditorAssetBrowser):
            raise TypeError("browser must be an EditorAssetBrowser")
        if browser.manager is not backend.manager:
            raise ValueError("asset workflow browser and pipeline must share one AssetManager")
        self.backend = backend
        self.browser = browser
        self._message = "Asset pipeline ready"

    @property
    def selected_path(self) -> str | None:
        entry = self.browser.selected_entry
        return None if entry is None else entry.relative_path

    def select(self, asset: str | Path | None) -> EditorAssetWorkflowFrame21:
        self.browser.select(asset)
        if asset is None:
            self._message = "Asset selection cleared"
        else:
            self._message = f"Selected {self.selected_path}"
        return self.frame()

    def refresh(self) -> EditorAssetWorkflowFrame21:
        completed = self.backend.poll()
        previous = self.selected_path
        self.browser.refresh()
        if previous is not None:
            try:
                self.browser.select(previous)
            except KeyError:
                previous = None
        if completed:
            succeeded = sum(result.successful for result in completed)
            self._message = f"Asset jobs finished: {succeeded}/{len(completed)} successful"
        return self.frame()

    def import_paths(
        self,
        paths: tuple[str | Path, ...] | list[str | Path],
        *,
        destination_folder: str | Path = "",
        overwrite: bool = False,
        submit: bool = True,
    ) -> tuple[EditorAssetImportTicket, ...]:
        tickets = self.backend.import_paths(
            paths,
            destination_folder=destination_folder,
            overwrite=overwrite,
            submit=submit,
        )
        self.browser.refresh()
        if tickets:
            self.browser.select(tickets[-1].relative_path)
        queued = sum(ticket.queued for ticket in tickets)
        self._message = f"Imported {len(tickets)} asset(s); {queued} background job(s) queued"
        return tickets

    def reimport_selected(self, *, submit: bool = True) -> EditorAssetImportTicket:
        selected = self.selected_path
        if selected is None:
            raise RuntimeError("select an asset before reimporting")
        ticket = self.backend.reimport(selected, submit=submit)
        self.browser.refresh()
        self.browser.select(selected)
        self._message = (
            f"Reimported {selected}"
            + (f"; job #{ticket.request_id} queued" if ticket.queued else "")
        )
        return ticket

    def frame(self) -> EditorAssetWorkflowFrame21:
        selected = self.selected_path
        preview: EditorAssetPreview | None = None
        dependencies: EditorAssetDependencyView | None = None
        issues: list[EditorAssetIssue] = []
        if selected is not None:
            issues.extend(self.backend.validate_asset(selected))
            try:
                preview = self.backend.preview(selected)
                dependencies = self.backend.dependencies(selected)
            except (OSError, EOFError, ValueError) as exc:
                issues.append(
                    EditorAssetIssue(
                        "preview_failed",
                        f"Could not inspect {selected}: {exc}",
                        EditorAssetIssueSeverity.WARNING,
                        "Refresh or reimport the asset and try the preview again.",
                    )
                )
        return EditorAssetWorkflowFrame21(
            self.backend.frame(),
            selected,
            preview,
            dependencies,
            tuple(issues),
            self._message,
        )

    def shutdown(self, *, wait: bool = True) -> None:
        self.backend.close(wait=wait)


class TkAssetPipelineEditorApp21(TkProductionViewportEditorApp21):
    """Production SwirEditor shell with an operational Asset Pipeline 2.1 tab."""

    def __init__(
        self,
        controller: Any,
        asset_workflow: EditorAssetWorkflow21,
        **kwargs: Any,
    ) -> None:
        if not isinstance(asset_workflow, EditorAssetWorkflow21):
            raise TypeError("asset_workflow must be an EditorAssetWorkflow21")
        self.asset_workflow = asset_workflow
        self._asset_paths: dict[str, str] = {}
        self._asset_preview_photo: Any = None
        super().__init__(controller, **kwargs)
        self.root.after(self.refresh_ms, self._poll_asset_pipeline)

    def _build(self) -> None:
        super()._build()
        ttk = self.ttk
        tk = self.tk

        self.assets_tree.bind("<<TreeviewSelect>>", self._asset_select, add="+")

        actions = ttk.Frame(self.assets_tab)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Import Files…", command=self._asset_import_files).pack(side="left")
        ttk.Button(actions, text="Import Folder…", command=self._asset_import_folder).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(actions, text="Reimport", command=self._asset_reimport).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(actions, text="Validate", command=self._asset_validate).pack(
            side="left", padx=(4, 0)
        )

        details = ttk.LabelFrame(self.assets_tab, text="Asset details", padding=6)
        details.pack(fill="x", pady=(6, 0))
        self.asset_details = tk.Text(details, height=7, wrap="word", state="disabled")
        self.asset_details.pack(fill="x")
        self.asset_pipeline_var = tk.StringVar(value="Asset pipeline ready")
        ttk.Label(details, textvariable=self.asset_pipeline_var, anchor="w").pack(
            fill="x", pady=(4, 0)
        )

    def _refresh_assets(self, frame: Any) -> None:
        super()._refresh_assets(frame)
        self._asset_paths.clear()
        selected = self.asset_workflow.selected_path
        for iid in self.assets_tree.get_children():
            path = str(self.assets_tree.item(iid, "text"))
            self._asset_paths[iid] = path
            if selected == path:
                self.assets_tree.selection_set(iid)
                self.assets_tree.see(iid)
        if hasattr(self, "asset_details"):
            self._refresh_asset_details(self.asset_workflow.frame())

    def _poll_asset_pipeline(self) -> None:
        if self._closed:
            return
        try:
            workflow_frame = self.asset_workflow.refresh()
            self.controller.refresh_assets()
            self._refresh_asset_details(workflow_frame)
        except (OSError, RuntimeError, ValueError) as exc:
            self.asset_pipeline_var.set(f"Asset pipeline error: {exc}")
        if not self._closed:
            self.root.after(self.refresh_ms, self._poll_asset_pipeline)

    def _asset_select(self, _event: object = None) -> None:
        selection = self.assets_tree.selection()
        if not selection:
            return
        path = self._asset_paths.get(selection[0])
        if path is None:
            path = str(self.assets_tree.item(selection[0], "text"))
        try:
            self._refresh_asset_details(self.asset_workflow.select(path))
        except (KeyError, OSError, ValueError) as exc:
            self.asset_pipeline_var.set(str(exc))

    def _asset_import_files(self) -> None:
        from tkinter import filedialog

        paths = tuple(filedialog.askopenfilenames(parent=self.root, title="Import assets"))
        if not paths:
            return
        self._run_asset_import(paths)

    def _asset_import_folder(self) -> None:
        from tkinter import filedialog

        path = filedialog.askdirectory(parent=self.root, title="Import asset folder")
        if not path:
            return
        self._run_asset_import((path,))

    def _run_asset_import(self, paths: tuple[str, ...]) -> None:
        try:
            tickets = self.asset_workflow.import_paths(paths)
            self.controller.refresh_assets()
            self._refresh_asset_details(self.asset_workflow.frame())
            self.asset_pipeline_var.set(
                f"Imported {len(tickets)} asset(s); "
                f"{sum(ticket.queued for ticket in tickets)} job(s) queued"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.asset_pipeline_var.set(str(exc))
            self.messagebox.showerror("SwirEditor — Asset import failed", str(exc), parent=self.root)

    def _asset_reimport(self) -> None:
        try:
            ticket = self.asset_workflow.reimport_selected()
            self.controller.refresh_assets()
            self._refresh_asset_details(self.asset_workflow.frame())
            self.asset_pipeline_var.set(
                f"Reimported {ticket.relative_path}"
                + (f"; job #{ticket.request_id} queued" if ticket.queued else "")
            )
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            self.asset_pipeline_var.set(str(exc))
            self.messagebox.showerror("SwirEditor — Reimport failed", str(exc), parent=self.root)

    def _asset_validate(self) -> None:
        frame = self.asset_workflow.frame()
        self._refresh_asset_details(frame)
        if frame.selected_path is None:
            self.asset_pipeline_var.set("Select an asset to validate")
        elif frame.healthy:
            self.asset_pipeline_var.set(f"{frame.selected_path}: validation passed")
        else:
            self.asset_pipeline_var.set(f"{frame.selected_path}: validation found blocking issues")

    def _refresh_asset_details(self, frame: EditorAssetWorkflowFrame21) -> None:
        if not hasattr(self, "asset_details"):
            return
        lines: list[str] = []
        if frame.selected_path is None:
            lines.append("Select an asset to inspect preview, dependencies and validation.")
        else:
            lines.append(frame.selected_path)
            if frame.preview is not None:
                lines.append(frame.preview.summary)
                if frame.preview.text:
                    preview_text = frame.preview.text
                    if len(preview_text) > 1200:
                        preview_text = preview_text[:1200] + "\n…"
                    lines.extend(("", preview_text))
            if frame.dependencies is not None:
                deps = frame.dependencies
                lines.append("")
                lines.append(
                    "Dependencies: "
                    + (", ".join(deps.dependencies) if deps.dependencies else "none")
                )
                lines.append(
                    "Dependents: " + (", ".join(deps.dependents) if deps.dependents else "none")
                )
            if frame.issues:
                lines.append("")
                lines.append("Validation:")
                for issue in frame.issues:
                    lines.append(f"- {issue.severity.value.upper()}: {issue.message}")
                    if issue.action:
                        lines.append(f"  Action: {issue.action}")

        diagnostics = frame.pipeline.diagnostics
        lines.append("")
        lines.append(
            "Jobs: "
            f"queued {diagnostics.queued} · running {diagnostics.running} · "
            f"completed {diagnostics.completed} · failed {diagnostics.failed}"
        )
        self.asset_details.configure(state="normal")
        self.asset_details.delete("1.0", "end")
        self.asset_details.insert("1.0", "\n".join(lines))
        self.asset_details.configure(state="disabled")
        self.asset_pipeline_var.set(frame.message)
