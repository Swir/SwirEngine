from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .assets import AssetManager
from .core.scene import Scene
from .editor_assets import EditorAssetBrowser
from .editor_diagnostics import EditorConsole, EditorProfiler
from .editor_frontend import EditorFrontendController, TkEditorApp
from .editor_workspace import EditorProjectState, EditorWorkspace
from .profiler import Profiler
from .project19 import ProjectManifest, ProjectManifestError
from .serialization import SceneSerializationError, SceneSerializer

DEFAULT_EDITOR_SCENE = "scenes/main.swirscene"
DEFAULT_EDITOR_STATE = ".swir/editor.json"


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


class EditorProjectSession:
    """Project-backed SwirEditor 2.1 session.

    The session composes the existing toolkit-neutral editor models into a safe creator workflow:
    manifest validation, scene load/save, portable editor-state persistence, asset browsing,
    diagnostics and the Tk desktop shell. Scene and editor-state writes are explicit and stay
    inside the project root.
    """

    def __init__(
        self,
        *,
        manifest: ProjectManifest,
        serializer: SceneSerializer,
        scene_path: Path,
        state_path: Path,
        workspace: EditorWorkspace,
        asset_browser: EditorAssetBrowser,
        console: EditorConsole,
        profiler: EditorProfiler,
        controller: EditorFrontendController,
    ) -> None:
        self.manifest = manifest
        self.serializer = serializer
        self.scene_path = scene_path
        self.state_path = state_path
        self.workspace = workspace
        self.asset_browser = asset_browser
        self.console = console
        self.profiler = profiler
        self.controller = controller

    @classmethod
    def open(
        cls,
        project: str | Path = ".",
        *,
        scene: str | Path = DEFAULT_EDITOR_SCENE,
        restore_state: bool = True,
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
        controller = EditorFrontendController(
            workspace,
            asset_browser=asset_browser,
            console=console,
            profiler=profiler,
        )
        console.write(
            f"Opened {manifest.name} ({manifest.mode})",
            source="swireditor",
        )
        return cls(
            manifest=manifest,
            serializer=serializer,
            scene_path=scene_path,
            state_path=state_path,
            workspace=workspace,
            asset_browser=asset_browser,
            console=console,
            profiler=profiler,
            controller=controller,
        )

    def summary(self) -> EditorProjectSummary:
        asset_frame = self.asset_browser.frame()
        return EditorProjectSummary(
            project_name=self.manifest.name,
            mode=self.manifest.mode,
            scene_path=self.scene_path.relative_to(self.manifest.root).as_posix(),
            scene_exists=self.scene_path.is_file(),
            editor_state_exists=self.state_path.is_file(),
            object_count=len(self.workspace.scene.objects),
            entity_count=len(self.workspace.scene.entities),
            asset_count=asset_frame.total_files,
        )

    def save(self) -> EditorProjectState:
        self.serializer.dump_scene(self.workspace.scene, self.scene_path)
        state = self.workspace.capture_project()
        state.save(self.state_path)
        self.console.write(
            f"Saved {self.scene_path.relative_to(self.manifest.root).as_posix()}",
            source="swireditor",
        )
        return state

    def run(self) -> None:
        app = TkEditorApp(
            self.controller,
            title=f"SwirEditor 2.1 — {self.manifest.name}",
        )
        self._install_file_menu(app)
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
        app.root.configure(menu=menu)
        app.root.bind_all("<Control-s>", lambda _event: self._save_from_ui(app))
        app.root.bind_all("<Control-S>", lambda _event: self._save_from_ui(app))
        app.root.protocol("WM_DELETE_WINDOW", lambda: self._close_from_ui(app))

    def _save_from_ui(self, app: TkEditorApp) -> None:
        try:
            self.save()
        except (OSError, SceneSerializationError, TypeError, ValueError) as exc:
            self.console.write(str(exc), level="error", source="swireditor")
            app.messagebox.showerror("SwirEditor — Save failed", str(exc))

    def _close_from_ui(self, app: TkEditorApp) -> None:
        try:
            self.save()
        except (OSError, SceneSerializationError, TypeError, ValueError) as exc:
            self.console.write(str(exc), level="error", source="swireditor")
            app.messagebox.showerror("SwirEditor — Save failed", str(exc))
            return
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        session = EditorProjectSession.open(
            args.project,
            scene=args.scene,
            restore_state=not args.fresh_layout,
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
        print(f"Assets: {summary.asset_count}")
        print(
            "Persistence: "
            f"scene={'present' if summary.scene_exists else 'new'}, "
            f"state={'present' if summary.editor_state_exists else 'new'}"
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
