from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .assets import AssetManager
from .core.scene import Scene
from .editor_assets import EditorAssetBrowser
from .editor_creator_frontend21 import (
    EditorCreatorFrontendController21,
    TkCreatorEditorApp21,
)
from .editor_diagnostics import EditorConsole, EditorProfiler
from .editor_frontend import TkEditorApp
from .editor_project_authoring21 import EditorProjectAuthoring21
from .editor_scene21 import EditorSceneAuthoring
from .editor_workspace import EditorProjectState, EditorWorkspace
from .profiler import Profiler
from .project19 import ProjectManifest, ProjectManifestError
from .serialization import SceneSerializationError, SceneSerializer

DEFAULT_EDITOR_SCENE = "scenes/main.swirscene"
DEFAULT_EDITOR_STATE = ".swir/editor.json"
RECOVERY_INTERVAL_MS = 30_000


class EditorProjectOpenError(RuntimeError):
    """Raised when a project cannot be opened safely by SwirEditor."""


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise ValueError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise ValueError(f"{label} must stay project-relative")
    return posix.as_posix()


@dataclass(frozen=True, slots=True)
class EditorProjectSummary:
    project_name: str
    mode: str
    scene_path: str
    scene_exists: bool
    editor_state_exists: bool
    object_count: int
    entity_count: int
    asset_count: int
    open_scenes: int = 1
    dirty: bool = False
    recovery_available: bool = False


class EditorProjectSession:
    """Project-backed SwirEditor 2.1 session.

    The session composes the existing toolkit-neutral editor models into a safe creator workflow:
    manifest validation, multi-scene authoring, portable editor-state persistence, asset browsing,
    typed multi-selection, component/prefab authoring, diagnostics, deterministic recovery and the
    Tk desktop shell. Scene and editor-state writes are explicit and stay inside the project root.
    """

    def __init__(
        self,
        *,
        manifest: ProjectManifest,
        serializer: SceneSerializer,
        scene_path: Path,
        state_path: Path,
        workspace: EditorWorkspace,
        authoring: EditorProjectAuthoring21,
        asset_browser: EditorAssetBrowser,
        console: EditorConsole,
        profiler: EditorProfiler,
        controller: EditorCreatorFrontendController21,
    ) -> None:
        self.manifest = manifest
        self.serializer = serializer
        self.scene_path = scene_path
        self.state_path = state_path
        self.workspace = workspace
        self.authoring = authoring
        self.asset_browser = asset_browser
        self.console = console
        self.profiler = profiler
        self.controller = controller
        self.scenes = EditorSceneAuthoring(
            manifest.root,
            serializer,
            workspace,
            initial_scene=scene_path.relative_to(manifest.root).as_posix(),
        )

    @classmethod
    def open(
        cls,
        project: str | Path = ".",
        *,
        scene: str | Path = DEFAULT_EDITOR_SCENE,
        restore_state: bool = True,
        restore_recovery: bool = False,
    ) -> EditorProjectSession:
        try:
            manifest = ProjectManifest.load(project)
        except (FileNotFoundError, ProjectManifestError) as exc:
            raise EditorProjectOpenError(str(exc)) from exc

        relative_scene = _project_relative_path(scene, label="editor scene path")
        scene_path = manifest.root / PurePosixPath(relative_scene)
        state_path = manifest.root / PurePosixPath(DEFAULT_EDITOR_STATE)
        serializer = SceneSerializer()

        if scene_path.is_file():
            try:
                live_scene = serializer.load_scene(scene_path)
            except (OSError, UnicodeError, SceneSerializationError) as exc:
                raise EditorProjectOpenError(
                    f"cannot load editor scene {relative_scene!r}: {exc}"
                ) from exc
        else:
            live_scene = Scene()

        workspace = EditorWorkspace(
            live_scene,
            scene_id=relative_scene,
            project_name=manifest.name,
            asset_root="assets",
        )
        if restore_state and state_path.is_file():
            try:
                state = EditorProjectState.load(state_path)
                workspace.restore_project(state, live_scene, scene_id=relative_scene)
            except (OSError, UnicodeError, TypeError, ValueError, LookupError) as exc:
                raise EditorProjectOpenError(
                    f"cannot restore {DEFAULT_EDITOR_STATE}: {exc}"
                ) from exc

        asset_browser = EditorAssetBrowser(AssetManager(manifest.root / "assets"))
        console = EditorConsole()
        profiler = EditorProfiler(Profiler())
        authoring = EditorProjectAuthoring21(
            workspace,
            serializer=serializer,
            asset_root=manifest.root / "assets",
        )
        controller = EditorCreatorFrontendController21(
            workspace,
            authoring,
            asset_browser=asset_browser,
            console=console,
            profiler=profiler,
        )
        console.write(
            f"Opened {manifest.name} ({manifest.mode})",
            source="swireditor",
        )
        session = cls(
            manifest=manifest,
            serializer=serializer,
            scene_path=scene_path,
            state_path=state_path,
            workspace=workspace,
            authoring=authoring,
            asset_browser=asset_browser,
            console=console,
            profiler=profiler,
            controller=controller,
        )
        if restore_recovery:
            if not session.scenes.recovery_available:
                raise EditorProjectOpenError("no SwirEditor recovery snapshot is available")
            try:
                session.scenes.restore_recovery()
            except (OSError, UnicodeError, TypeError, ValueError) as exc:
                raise EditorProjectOpenError(f"cannot restore editor recovery: {exc}") from exc
            console.write("Recovered unsaved SwirEditor state", source="swireditor")
        return session

    def summary(self) -> EditorProjectSummary:
        asset_frame = self.asset_browser.frame()
        active_path = self.scenes.active_path
        active_scene = self.workspace.scene
        return EditorProjectSummary(
            project_name=self.manifest.name,
            mode=self.manifest.mode,
            scene_path=active_path,
            scene_exists=(self.manifest.root / PurePosixPath(active_path)).is_file(),
            editor_state_exists=self.state_path.is_file(),
            object_count=len(active_scene.objects),
            entity_count=len(active_scene.entities),
            asset_count=asset_frame.total_files,
            open_scenes=len(self.scenes.scene_paths),
            dirty=self.scenes.dirty,
            recovery_available=self.scenes.recovery_available,
        )

    def save(self) -> EditorProjectState:
        state = self.scenes.save_all(self.state_path)
        self.scene_path = self.manifest.root / PurePosixPath(self.scenes.active_path)
        self.console.write(
            f"Saved {len(self.scenes.scene_paths)} open scene(s)",
            source="swireditor",
        )
        return state

    def run(self) -> None:
        app = TkCreatorEditorApp21(
            self.controller,
            title=f"SwirEditor 2.1 — {self.manifest.name}",
        )
        self._install_file_menu(app)
        self._schedule_recovery(app)
        app.run()

    def _install_file_menu(self, app: TkEditorApp) -> None:
        tk = app.tk
        menu = tk.Menu(app.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(
            label="Save Project",
            accelerator="Ctrl+S",
            command=lambda: self._save_from_ui(app),
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=lambda: self._close_from_ui(app))
        menu.add_cascade(label="File", menu=file_menu)
        if isinstance(app, TkCreatorEditorApp21):
            app.install_creator_menu(menu)
        app.root.configure(menu=menu)
        app.root.bind_all("<Control-s>", lambda _event: self._save_from_ui(app))
        app.root.bind_all("<Control-S>", lambda _event: self._save_from_ui(app))
        app.root.protocol("WM_DELETE_WINDOW", lambda: self._close_from_ui(app))

    def _schedule_recovery(self, app: TkEditorApp) -> None:
        def checkpoint() -> None:
            if getattr(app, "_closed", False):
                return
            if self.scenes.dirty:
                try:
                    self.scenes.write_recovery()
                except (
                    OSError,
                    UnicodeError,
                    TypeError,
                    ValueError,
                    SceneSerializationError,
                ) as exc:
                    self.console.write(str(exc), level="error", source="recovery")
            if not getattr(app, "_closed", False):
                app.root.after(RECOVERY_INTERVAL_MS, checkpoint)

        app.root.after(RECOVERY_INTERVAL_MS, checkpoint)

    def _save_from_ui(self, app: TkEditorApp) -> None:
        try:
            self.save()
        except (OSError, SceneSerializationError, TypeError, ValueError) as exc:
            self.console.write(str(exc), level="error", source="swireditor")
            app.messagebox.showerror("SwirEditor — Save failed", str(exc))

    def _close_from_ui(self, app: TkEditorApp) -> None:
        if self.scenes.dirty:
            decision = app.messagebox.askyesnocancel(
                "SwirEditor — Unsaved changes",
                "Save project changes before closing?",
                parent=app.root,
            )
            if decision is None:
                return
            if decision:
                try:
                    self.save()
                except (OSError, SceneSerializationError, TypeError, ValueError) as exc:
                    self.console.write(str(exc), level="error", source="swireditor")
                    app.messagebox.showerror(
                        "SwirEditor — Save failed", str(exc), parent=app.root
                    )
                    return
            else:
                self.scenes.discard_recovery()
        app.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swireditor",
        description="Open a SwirEngine project in the SwirEditor 2.1 desktop shell.",
    )
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument(
        "--scene",
        default=DEFAULT_EDITOR_SCENE,
        help=f"project-relative scene file (default: {DEFAULT_EDITOR_SCENE})",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="validate and inspect the editor project without opening a window",
    )
    parser.add_argument(
        "--fresh-layout",
        action="store_true",
        help=f"ignore saved {DEFAULT_EDITOR_STATE} layout/selection state for this launch",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="restore the deterministic .swir recovery snapshot before opening",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        session = EditorProjectSession.open(
            args.project,
            scene=args.scene,
            restore_state=not args.fresh_layout,
            restore_recovery=args.recover,
        )
    except (EditorProjectOpenError, ValueError) as exc:
        print(f"SwirEditor failed: {exc}")
        return 2

    if args.headless:
        summary = session.summary()
        print(f"SwirEditor 2.1 project: {summary.project_name} ({summary.mode})")
        print(
            f"Scene: {summary.scene_path} "
            f"({summary.object_count} objects, {summary.entity_count} entities)"
        )
        print(f"Open scenes: {summary.open_scenes}")
        print(f"Assets: {summary.asset_count}")
        print(
            "Persistence: "
            f"scene={'present' if summary.scene_exists else 'new'}, "
            f"state={'present' if summary.editor_state_exists else 'new'}, "
            f"dirty={'yes' if summary.dirty else 'no'}, "
            f"recovery={'yes' if summary.recovery_available else 'no'}"
        )
        return 0

    try:
        session.run()
    except RuntimeError as exc:
        print(f"SwirEditor failed: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
