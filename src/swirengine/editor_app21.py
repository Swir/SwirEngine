from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .assets import AssetManager
from .core.scene import Scene
from .editor_assets import EditorAssetBrowser
from .editor_diagnostics import EditorConsole, EditorProfiler
from .editor_frontend import EditorFrontendController, TkEditorApp
from .editor_preview import EditorPreviewSession
from .editor_workspace import EditorProjectState, EditorWorkspace
from .profiler import Profiler
from .project19 import ProjectManifest, ProjectManifestError
from .serialization import SceneSerializationError, SceneSerializer
from .shipping19 import ProjectShippingDefaults

EDITOR_STATE_FILE = ".swir/editor.json"
DEFAULT_SCENE_ID = "scenes/main.swirscene"
ProjectFactory = Callable[[str, str], Path]

_TEMPLATE_2D = """from swirengine import Color, Game, Rectangle2D

game = Game("{name}", 1280, 720, mode="2d")
player = game.add(Rectangle2D(0, 0, 140, 80, Color(0.1, 0.7, 1.0, 1.0), name="player"))

@game.update
def update(dt):
    speed = 400
    if game.key("A"):
        player.x -= speed * dt
    if game.key("D"):
        player.x += speed * dt
    if game.key("W"):
        player.y += speed * dt
    if game.key("S"):
        player.y -= speed * dt

game.run()
"""

_TEMPLATE_3D = """from swirengine import Color, Cube3D, Game, Vec3

game = Game("{name}", 1280, 720, mode="3d")
cube = Cube3D(position=Vec3(0, 0, -4), color=Color(0.2, 0.7, 1.0, 1.0))
game.add(cube)

@game.update
def update(dt):
    cube.rotation.y += 50 * dt
    cube.rotation.x += 25 * dt

game.run()
"""


class EditorProjectError(RuntimeError):
    """Raised when an editor project cannot be opened or persisted safely."""


@dataclass(frozen=True, slots=True)
class EditorSaveResult:
    scene_path: Path
    state_path: Path


def _safe_project_relative(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    portable = raw.replace("\\", "/")
    path = PurePosixPath(portable)
    windows = PureWindowsPath(raw)
    if (
        not portable
        or portable == "."
        or path.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in path.parts
    ):
        raise EditorProjectError(f"{label} must stay project-relative")
    return path.as_posix()


def _scene_path(root: Path, scene_id: str) -> Path:
    normalized = _safe_project_relative(scene_id, label="editor scene id")
    path = PurePosixPath(normalized)
    if path.suffix != ".swirscene":
        if path.parts and path.parts[0] == "scenes":
            path = path.with_suffix(".swirscene")
        else:
            path = PurePosixPath("scenes") / f"{path.as_posix()}.swirscene"
    return root.joinpath(*path.parts)


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def create_editor_project(path: str | Path, mode: str = "2d") -> Path:
    """Create a SwirEngine 2.x project ready to open in SwirEditor."""

    if mode not in {"2d", "3d"}:
        raise ValueError("mode must be '2d' or '3d'")
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    project_name = root.name
    for sub in ("assets", "scenes", "prefabs", "scripts", "settings", "config"):
        (root / sub).mkdir()
    template = _TEMPLATE_3D if mode == "3d" else _TEMPLATE_2D
    (root / "main.py").write_text(template.format(name=project_name), encoding="utf-8")
    quoted_name = _toml_quote(project_name)
    quoted_mode = _toml_quote(mode)
    manifest = f"""name = {quoted_name}
mode = {quoted_mode}
engine = ">=2.0,<3.0"
entrypoint = "main.py"

[content]
include = ["assets", "scenes", "prefabs", "scripts", "config"]

[run]
entrypoint = "main.py"
working_directory = "."
arguments = []
inherit_environment = true

[profiles.windows]
target = "windows"
app_name = {quoted_name}
onefile = false
console = true

[profiles.linux]
target = "linux"
app_name = {quoted_name}
onefile = false
console = true

[profiles.macos]
target = "macos"
app_name = {quoted_name}
onefile = false
console = true
"""
    (root / "swirproject.toml").write_text(manifest, encoding="utf-8")
    ProjectShippingDefaults.load(root).write_templates()
    (root / ".gitignore").write_text(
        "__pycache__/\n.venv/\nbuild/\ndist/\n.swir/session/\n",
        encoding="utf-8",
    )
    return root


@dataclass(slots=True)
class EditorProjectSession:
    root: Path
    manifest: ProjectManifest
    scene_path: Path
    state_path: Path
    serializer: SceneSerializer
    workspace: EditorWorkspace
    assets: EditorAssetBrowser
    console: EditorConsole
    profiler: EditorProfiler
    preview: EditorPreviewSession
    controller: EditorFrontendController

    @classmethod
    def open(cls, project: str | Path = ".") -> EditorProjectSession:
        try:
            manifest = ProjectManifest.load(project)
        except (FileNotFoundError, ProjectManifestError) as exc:
            raise EditorProjectError(str(exc)) from exc

        state_path = manifest.root / EDITOR_STATE_FILE
        state: EditorProjectState | None = None
        if state_path.is_file():
            try:
                state = EditorProjectState.load(state_path)
            except (OSError, TypeError, ValueError) as exc:
                raise EditorProjectError(f"cannot load editor state: {exc}") from exc

        scene_id = DEFAULT_SCENE_ID if state is None else state.active_scene_id
        scene_path = _scene_path(manifest.root, scene_id)
        serializer = SceneSerializer()
        try:
            scene = serializer.load_scene(scene_path) if scene_path.is_file() else Scene()
        except (OSError, SceneSerializationError, TypeError, ValueError) as exc:
            raise EditorProjectError(f"cannot load editor scene {scene_id!r}: {exc}") from exc

        asset_root = "assets" if state is None else state.asset_root
        safe_asset_root = _safe_project_relative(asset_root, label="editor asset root")
        workspace = EditorWorkspace(
            scene,
            scene_id=scene_id,
            project_name=manifest.name,
            asset_root=safe_asset_root,
        )
        if state is not None:
            try:
                workspace.restore_project(state, scene, scene_id=scene_id)
            except (KeyError, LookupError, TypeError, ValueError) as exc:
                raise EditorProjectError(f"cannot restore editor workspace: {exc}") from exc

        assets = EditorAssetBrowser(AssetManager(manifest.root / safe_asset_root))
        console = EditorConsole()
        console.write(f"Opened {manifest.name}", source="SwirEditor")
        profiler = EditorProfiler(Profiler())
        preview = EditorPreviewSession(workspace)
        controller = EditorFrontendController(
            workspace,
            asset_browser=assets,
            console=console,
            profiler=profiler,
            preview=preview,
        )
        return cls(
            manifest.root,
            manifest,
            scene_path,
            state_path,
            serializer,
            workspace,
            assets,
            console,
            profiler,
            preview,
            controller,
        )

    def save(self) -> EditorSaveResult:
        scene_path = _scene_path(self.root, self.workspace.scene_id)
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        self.serializer.dump_scene(self.workspace.scene, scene_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace.capture_project().save(self.state_path)
        self.scene_path = scene_path
        self.console.write(
            f"Saved {scene_path.relative_to(self.root).as_posix()}",
            source="SwirEditor",
        )
        return EditorSaveResult(scene_path, self.state_path)

    def launch(self) -> None:
        app = TkEditorApp(
            self.controller,
            title=f"SwirEditor 2.1 — {self.manifest.name}",
            refresh_ms=100,
        )

        def save_binding(_event=None):
            try:
                self.save()
            except (
                OSError,
                EditorProjectError,
                SceneSerializationError,
                TypeError,
                ValueError,
            ) as exc:
                app.status_var.set(f"Save failed: {exc}")
            else:
                app.status_var.set("Project saved")
            return "break"

        def close_with_save() -> None:
            try:
                self.save()
            except (
                OSError,
                EditorProjectError,
                SceneSerializationError,
                TypeError,
                ValueError,
            ) as exc:
                self.console.write(f"Autosave failed: {exc}", source="SwirEditor")
            app.close()

        app.root.bind_all("<Control-s>", save_binding)
        app.root.bind_all("<Command-s>", save_binding)
        app.root.protocol("WM_DELETE_WINDOW", close_with_save)
        app.run()


class TkProjectHub:
    """Dark project hub that opens or creates projects before the main editor shell."""

    def __init__(self, project_factory: ProjectFactory = create_editor_project) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog, messagebox, ttk
        except ImportError as exc:  # pragma: no cover - platform packaging detail
            raise RuntimeError("Tkinter is required for SwirEditor") from exc

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.project_factory = project_factory
        self.result: Path | None = None

        self.root = tk.Tk()
        self.root.title("SwirEditor 2.1 — Project Hub")
        self.root.geometry("760x460")
        self.root.minsize(680, 420)
        self.root.configure(bg="#02050A")

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Hub.TFrame", background="#02050A")
        style.configure("Panel.TFrame", background="#07111C")
        style.configure(
            "Title.TLabel",
            background="#02050A",
            foreground="#F4FAFF",
            font=("Segoe UI", 22, "bold"),
        )
        style.configure(
            "Sub.TLabel",
            background="#02050A",
            foreground="#8DA8B8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Panel.TLabel",
            background="#07111C",
            foreground="#F4FAFF",
            font=("Segoe UI", 10),
        )
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

        shell = ttk.Frame(self.root, style="Hub.TFrame", padding=26)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="SwirEditor 2.1", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="Create or open a SwirEngine project, then continue in the visual editor.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 20))

        panel = ttk.Frame(shell, style="Panel.TFrame", padding=20)
        panel.pack(fill="both", expand=True)

        ttk.Label(panel, text="New project", style="Panel.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        self.name_var = tk.StringVar(value="MyGame")
        ttk.Entry(panel, textvariable=self.name_var).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 12)
        )
        self.mode_var = tk.StringVar(value="2d")
        ttk.Combobox(
            panel,
            textvariable=self.mode_var,
            values=("2d", "3d"),
            state="readonly",
            width=8,
        ).grid(row=1, column=2, sticky="e", padx=(10, 0), pady=(8, 12))
        ttk.Button(
            panel,
            text="Create project",
            style="Accent.TButton",
            command=self._create,
        ).grid(row=2, column=0, columnspan=3, sticky="ew")

        ttk.Separator(panel).grid(row=3, column=0, columnspan=3, sticky="ew", pady=22)
        ttk.Label(panel, text="Existing project", style="Panel.TLabel").grid(
            row=4, column=0, columnspan=3, sticky="w"
        )
        ttk.Button(
            panel,
            text="Open swirproject.toml",
            command=self._open,
        ).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def choose(self) -> Path | None:
        self.root.mainloop()
        return self.result

    def _create(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            self.messagebox.showerror("SwirEditor", "Project name cannot be empty.")
            return
        parent = self.filedialog.askdirectory(title="Choose project parent folder")
        if not parent:
            return
        target = Path(parent) / name
        try:
            created = self.project_factory(str(target), self.mode_var.get())
        except (FileExistsError, OSError, ValueError) as exc:
            self.messagebox.showerror("SwirEditor", f"Cannot create project:\n{exc}")
            return
        self.result = Path(created)
        self.root.destroy()

    def _open(self) -> None:
        manifest = self.filedialog.askopenfilename(
            title="Open SwirEngine project",
            filetypes=(("SwirEngine project", "swirproject.toml"), ("TOML files", "*.toml")),
        )
        if not manifest:
            return
        path = Path(manifest)
        if path.name != "swirproject.toml":
            self.messagebox.showerror("SwirEditor", "Select a swirproject.toml file.")
            return
        self.result = path.parent
        self.root.destroy()


def run_editor_cli(
    project: str | Path | None = None,
    *,
    new_name: str | None = None,
    mode: str = "2d",
    project_factory: ProjectFactory = create_editor_project,
) -> int:
    if project is not None and new_name is not None:
        print("Editor start failed: project and --new are mutually exclusive", file=sys.stderr)
        return 2
    try:
        if new_name is not None:
            root = project_factory(new_name, mode)
        elif project is not None:
            root = Path(project)
        else:
            chosen = TkProjectHub(project_factory).choose()
            if chosen is None:
                return 0
            root = chosen
        session = EditorProjectSession.open(root)
        session.launch()
    except (
        EditorProjectError,
        FileExistsError,
        FileNotFoundError,
        OSError,
        ProjectManifestError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"Editor start failed: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="swireditor")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--new", dest="new_name")
    parser.add_argument("--mode", choices=("2d", "3d"), default="2d")
    args = parser.parse_args(argv)
    return run_editor_cli(args.project, new_name=args.new_name, mode=args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
