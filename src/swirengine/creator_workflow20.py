from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .content_build19 import ContentBuildError, ContentBuildGraph
from .editor_workflow import EditorProjectLayout
from .game_state19 import GameStateProductionError, project_app_id, resolve_user_data_root
from .project19 import ProjectDiagnostic, ProjectManifest, ProjectManifestError
from .run_sessions19 import RunSessionError, create_run_plan
from .scene_packages19 import ScenePackageError, ScenePackageRegistry
from .serialization import SceneSerializer
from .shipping19 import ProjectShippingDefaults, ShippingContractError


@dataclass(frozen=True, slots=True)
class CreatorWorkflowDiagnostic:
    """Actionable project-level diagnostic for the integrated creator workflow."""

    severity: str
    code: str
    message: str
    source: str
    path: str | None = None
    action: str | None = None

    def to_dict(self) -> dict[str, str]:
        data = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source": self.source,
        }
        if self.path is not None:
            data["path"] = self.path
        if self.action is not None:
            data["action"] = self.action
        return data


@dataclass(frozen=True, slots=True)
class CreatorProjectReport:
    """Portable inspection snapshot for one creator project."""

    name: str
    mode: str | None
    manifest_fingerprint: str | None
    profiles: tuple[str, ...]
    selected_profile: str | None
    run_plan_fingerprint: str | None
    scene_packages: int
    scene_fingerprint: str | None
    content_nodes: int
    content_fingerprint: str | None
    shipping_defaults_fingerprint: str | None
    input_defaults_present: bool
    settings_defaults_present: bool
    user_data_platform: str | None
    user_data_source: str | None
    editor_directories: tuple[str, ...]
    diagnostics: tuple[CreatorWorkflowDiagnostic, ...]
    fingerprint: str

    @property
    def ready(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "ready": self.ready,
            "manifest_fingerprint": self.manifest_fingerprint,
            "profiles": list(self.profiles),
            "selected_profile": self.selected_profile,
            "run_plan_fingerprint": self.run_plan_fingerprint,
            "scene_packages": self.scene_packages,
            "scene_fingerprint": self.scene_fingerprint,
            "content_nodes": self.content_nodes,
            "content_fingerprint": self.content_fingerprint,
            "shipping_defaults_fingerprint": self.shipping_defaults_fingerprint,
            "input_defaults_present": self.input_defaults_present,
            "settings_defaults_present": self.settings_defaults_present,
            "user_data_platform": self.user_data_platform,
            "user_data_source": self.user_data_source,
            "editor_directories": list(self.editor_directories),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "fingerprint": self.fingerprint,
        }


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _action_for(code: str, path: str | None) -> str:
    target = path or "the referenced project setting"
    if code in {"entrypoint-missing", "run-entrypoint-missing", "profile-entrypoint-missing"}:
        return f"Create {target} or update the matching entrypoint in swirproject.toml."
    if code in {"content-missing", "profile-content-missing"}:
        return f"Create {target} or remove it from the matching content include list."
    if code == "profile-icon-missing":
        return f"Create {target} or remove/update the profile icon setting."
    if code.startswith("content-build"):
        return f"Fix the content.build declaration or required file for {target}."
    if code.startswith("scene-package"):
        return f"Fix the [scenes] declaration or scene/prefab document for {target}."
    return "Review swirproject.toml and the referenced project file."


def _convert_diagnostic(
    item: ProjectDiagnostic,
    *,
    source: str,
) -> CreatorWorkflowDiagnostic:
    return CreatorWorkflowDiagnostic(
        severity=item.severity,
        code=item.code,
        message=item.message,
        source=source,
        path=item.path,
        action=_action_for(item.code, item.path),
    )


class CreatorProjectWorkflow:
    """Integrated project inspection/preparation surface for SwirEngine 2.0 creators.

    It composes the established project, run-session, scene-package, content-build,
    shipping-settings and user-data contracts. Inspection never executes a game,
    mutates save data or performs an export.
    """

    def __init__(self, project: str | Path = ".") -> None:
        source = Path(project).expanduser()
        self.root = (source.parent if source.name == "swirproject.toml" else source).resolve()
        self.layout = EditorProjectLayout.at(self.root)

    def prepare(self) -> tuple[Path, ...]:
        """Create missing creator directories/defaults without overwriting user files."""

        # Validate the project before any mutation so a typo/wrong working directory cannot
        # litter an unrelated directory with creator folders or configuration templates.
        ProjectManifest.load(self.root)

        created: list[Path] = []
        for directory in (
            self.layout.scenes_dir,
            self.layout.prefabs_dir,
            self.layout.settings_dir,
        ):
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                created.append(directory)

        defaults = ProjectShippingDefaults.load(self.root)
        controls = self.root / "config" / "controls.json"
        settings = self.root / "config" / "settings.json"
        if not controls.exists():
            defaults.actions.save(controls)
            created.append(controls)
        if not settings.exists():
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(
                json.dumps(defaults.settings.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            created.append(settings)
        return tuple(created)

    def inspect(
        self,
        *,
        profile_name: str | None = None,
        platform: str | None = None,
        environ: dict[str, str] | None = None,
        home: str | Path | None = None,
        validate_documents: bool = True,
    ) -> CreatorProjectReport:
        diagnostics: list[CreatorWorkflowDiagnostic] = []
        values: dict[str, Any] = {
            "name": self.root.name,
            "mode": None,
            "manifest_fingerprint": None,
            "profiles": (),
            "selected_profile": None,
            "run_plan_fingerprint": None,
            "scene_packages": 0,
            "scene_fingerprint": None,
            "content_nodes": 0,
            "content_fingerprint": None,
            "shipping_defaults_fingerprint": None,
            "input_defaults_present": False,
            "settings_defaults_present": False,
            "user_data_platform": None,
            "user_data_source": None,
        }

        try:
            manifest = ProjectManifest.load(self.root)
        except FileNotFoundError as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "manifest-missing",
                    str(exc),
                    "project",
                    "swirproject.toml",
                    "Create the project with `swirengine new` or add a valid swirproject.toml.",
                )
            )
            return self._report(values, diagnostics)
        except ProjectManifestError as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "manifest-invalid",
                    str(exc),
                    "project",
                    "swirproject.toml",
                    "Fix the TOML/project fields reported above and run the workflow check again.",
                )
            )
            return self._report(values, diagnostics)

        values.update(
            name=manifest.name,
            mode=manifest.mode,
            manifest_fingerprint=manifest.fingerprint,
            profiles=tuple(sorted(manifest.profiles)),
        )

        if profile_name is not None:
            try:
                profile = manifest.packaging_profile(profile_name)
            except ProjectManifestError as exc:
                diagnostics.append(
                    CreatorWorkflowDiagnostic(
                        "error",
                        "profile-invalid",
                        str(exc),
                        "export",
                        action="Choose a declared packaging profile or add it to swirproject.toml.",
                    )
                )
            else:
                values["selected_profile"] = profile.name

        try:
            manifest_diagnostics = manifest.diagnostics(profile_name=profile_name)
        except ProjectManifestError as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "profile-invalid",
                    str(exc),
                    "project",
                    action="Choose a declared packaging profile or update swirproject.toml.",
                )
            )
        else:
            diagnostics.extend(
                _convert_diagnostic(item, source="project") for item in manifest_diagnostics
            )

        try:
            run_plan = create_run_plan(manifest)
        except RunSessionError as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "run-plan-invalid",
                    str(exc),
                    "run",
                    action="Fix the [run] entrypoint, working directory or environment declaration.",
                )
            )
        else:
            values["run_plan_fingerprint"] = run_plan.fingerprint

        try:
            registry = ScenePackageRegistry.load_optional(manifest)
        except ScenePackageError as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "scene-package-invalid",
                    str(exc),
                    "scenes",
                    "swirproject.toml",
                    "Fix the [scenes] registry, paths or dependency graph.",
                )
            )
        else:
            if registry is not None:
                values["scene_packages"] = len(registry.packages)
                values["scene_fingerprint"] = registry.fingerprint
                diagnostics.extend(
                    _convert_diagnostic(item, source="scenes") for item in registry.diagnostics()
                )
                if validate_documents:
                    diagnostics.extend(
                        _convert_diagnostic(item, source="scenes")
                        for item in registry.validate_documents(SceneSerializer())
                    )

        try:
            graph = ContentBuildGraph.load_optional(manifest)
        except ContentBuildError as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "content-build-invalid",
                    str(exc),
                    "content",
                    "swirproject.toml",
                    "Fix the [content.build] nodes, paths or dependency graph.",
                )
            )
        else:
            if graph is not None:
                values["content_nodes"] = len(graph.nodes)
                values["content_fingerprint"] = graph.fingerprint
                diagnostics.extend(
                    _convert_diagnostic(item, source="content") for item in graph.diagnostics()
                )

        try:
            defaults = ProjectShippingDefaults.load(self.root)
        except (OSError, ValueError, ShippingContractError) as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "shipping-defaults-invalid",
                    str(exc),
                    "settings",
                    action="Fix config/controls.json or config/settings.json and run the check again.",
                )
            )
        else:
            values["shipping_defaults_fingerprint"] = defaults.fingerprint
            values["input_defaults_present"] = defaults.input_source is not None
            values["settings_defaults_present"] = defaults.settings_source is not None
            if defaults.input_source is None:
                diagnostics.append(
                    CreatorWorkflowDiagnostic(
                        "warning",
                        "input-defaults-missing",
                        "project input defaults are using built-in fallback bindings",
                        "settings",
                        "config/controls.json",
                        "Run `swirengine workflow . --prepare` to materialize editable defaults.",
                    )
                )
            if defaults.settings_source is None:
                diagnostics.append(
                    CreatorWorkflowDiagnostic(
                        "warning",
                        "settings-defaults-missing",
                        "project display/accessibility defaults are using built-in fallback values",
                        "settings",
                        "config/settings.json",
                        "Run `swirengine workflow . --prepare` to materialize editable defaults.",
                    )
                )

        try:
            location = resolve_user_data_root(
                project_app_id(manifest.name),
                platform=platform,
                environ=environ,
                home=home,
            )
        except (GameStateProductionError, OSError, ValueError) as exc:
            diagnostics.append(
                CreatorWorkflowDiagnostic(
                    "error",
                    "user-data-policy-invalid",
                    str(exc),
                    "save-data",
                    action="Use a project name that maps to a valid application id.",
                )
            )
        else:
            values["user_data_platform"] = location.platform
            values["user_data_source"] = location.source

        for relative, directory in (
            ("scenes", self.layout.scenes_dir),
            ("prefabs", self.layout.prefabs_dir),
            ("settings", self.layout.settings_dir),
        ):
            if not directory.is_dir():
                diagnostics.append(
                    CreatorWorkflowDiagnostic(
                        "warning",
                        "creator-directory-missing",
                        f"creator directory {relative!r} does not exist",
                        "editor",
                        relative,
                        "Run `swirengine workflow . --prepare` to create creator directories.",
                    )
                )

        return self._report(values, diagnostics)

    def _report(
        self,
        values: dict[str, Any],
        diagnostics: list[CreatorWorkflowDiagnostic],
    ) -> CreatorProjectReport:
        editor_directories = tuple(
            relative
            for relative, directory in (
                ("scenes", self.layout.scenes_dir),
                ("prefabs", self.layout.prefabs_dir),
                ("settings", self.layout.settings_dir),
            )
            if directory.is_dir()
        )
        portable = {
            **values,
            "profiles": list(values["profiles"]),
            "editor_directories": list(editor_directories),
            "diagnostics": [item.to_dict() for item in diagnostics],
        }
        return CreatorProjectReport(
            **values,
            editor_directories=editor_directories,
            diagnostics=tuple(diagnostics),
            fingerprint=_fingerprint(portable),
        )


def inspect_creator_project(
    project: str | Path = ".",
    *,
    profile_name: str | None = None,
    prepare: bool = False,
    validate_documents: bool = True,
) -> CreatorProjectReport:
    workflow = CreatorProjectWorkflow(project)
    if prepare:
        workflow.prepare()
    return workflow.inspect(
        profile_name=profile_name,
        validate_documents=validate_documents,
    )


__all__ = [
    "CreatorProjectReport",
    "CreatorProjectWorkflow",
    "CreatorWorkflowDiagnostic",
    "inspect_creator_project",
]
