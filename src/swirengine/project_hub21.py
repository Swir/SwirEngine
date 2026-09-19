from __future__ import annotations

import json
from pathlib import Path

from .editor_app21 import EditorProjectOpenError, EditorProjectSession
from .project19 import ProjectManifest, ProjectManifestError
from .project_scaffold21 import new_project21

RECENT_PROJECT_LIMIT = 12


class RecentProjectsStore:
    """Host-local, bounded MRU list used by the SwirEditor Project Hub."""

    def __init__(self, path: str | Path | None = None, *, limit: int = RECENT_PROJECT_LIMIT) -> None:
        if limit < 1:
            raise ValueError("recent project limit must be at least 1")
        self.path = (
            Path.home() / ".swirengine" / "recent-projects.json"
            if path is None
            else Path(path).expanduser()
        )
        self.limit = int(limit)

    def load(self) -> tuple[Path, ...]:
        if not self.path.is_file():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ()
        if not isinstance(payload, list):
            return ()

        projects: list[Path] = []
        seen: set[str] = set()
        for item in payload:
            if not isinstance(item, str):
                continue
            candidate = Path(item).expanduser().resolve()
            key = str(candidate)
            if key in seen or not (candidate / "swirproject.toml").is_file():
                continue
            projects.append(candidate)
            seen.add(key)
            if len(projects) >= self.limit:
                break
        return tuple(projects)

    def record(self, project: str | Path) -> tuple[Path, ...]:
        root = Path(project).expanduser().resolve()
        if not (root / "swirproject.toml").is_file():
            raise FileNotFoundError(f"SwirEngine project manifest not found: {root}")
        projects = [root]
        projects.extend(path for path in self.load() if path != root)
        projects = projects[: self.limit]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps([str(path) for path in projects], indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return tuple(projects)


class EditorProjectHub:
    """Toolkit-neutral New/Open/Recent project workflow for SwirEditor 2.1."""

    def __init__(self, recent: RecentProjectsStore | None = None) -> None:
        self.recent = recent or RecentProjectsStore()

    def recent_projects(self) -> tuple[Path, ...]:
        return self.recent.load()

    def open_project(self, project: str | Path) -> EditorProjectSession:
        session = EditorProjectSession.open(project)
        self._remember(session.manifest.root)
        return session

    def create_project(self, name: str, mode: str, *, parent: str | Path) -> EditorProjectSession:
        root = new_project21(name, mode, parent=parent)
        session = EditorProjectSession.open(root)
        self._remember(root)
        return session

    def _remember(self, root: Path) -> None:
        try:
            self.recent.record(root)
        except OSError:
            # A read-only home directory must never block opening a valid game project.
            pass


class TkProjectHubApp:
    """Native New/Open/Recent hub that hands a validated session to SwirEditor."""

    def __init__(self, hub: EditorProjectHub | None = None) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog, messagebox, simpledialog, ttk
        except ImportError as exc:  # pragma: no cover - platform packaging detail
            raise RuntimeError("Tkinter is required for the SwirEditor Project Hub") from exc

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.simpledialog = simpledialog
        self.hub = hub or EditorProjectHub()
        self.session: EditorProjectSession | None = None
        self._recent_by_iid: dict[str, Path] = {}
        self.root = tk.Tk()
        self.root.title("SwirEditor 2.1 — Project Hub")
        self.root.geometry("760x500")
        self.root.minsize(640, 420)
        self.root.configure(bg="#02050A")
        self._style()
        self._build()
        self._refresh_recent()

    def choose(self) -> EditorProjectSession | None:
        self.root.mainloop()
        return self.session

    def _style(self) -> None:
        style = self.ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Hub.TFrame", background="#02050A")
        style.configure("HubCard.TFrame", background="#07111C")
        style.configure(
            "HubTitle.TLabel",
            background="#02050A",
            foreground="#F4FAFF",
            font=("Segoe UI", 24, "bold"),
        )
        style.configure(
            "HubSub.TLabel",
            background="#02050A",
            foreground="#8DA8B8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Hub.TButton",
            background="#07111C",
            foreground="#F4FAFF",
            padding=(14, 8),
        )
        style.map("Hub.TButton", background=[("active", "#0088FF")])
        style.configure(
            "Treeview",
            background="#07111C",
            fieldbackground="#07111C",
            foreground="#F4FAFF",
            rowheight=30,
        )
        style.map("Treeview", background=[("selected", "#0088FF")])

    def _build(self) -> None:
        ttk = self.ttk
        outer = ttk.Frame(self.root, padding=24, style="Hub.TFrame")
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="SwirEditor", style="HubTitle.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Create, reopen and continue SwirEngine 2D/3D projects.",
            style="HubSub.TLabel",
        ).pack(anchor="w", pady=(2, 18))

        actions = ttk.Frame(outer, style="Hub.TFrame")
        actions.pack(fill="x", pady=(0, 16))
        ttk.Button(
            actions,
            text="New 2D Project",
            style="Hub.TButton",
            command=lambda: self._new_project("2d"),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="New 3D Project",
            style="Hub.TButton",
            command=lambda: self._new_project("3d"),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Open Project…",
            style="Hub.TButton",
            command=self._open_project,
        ).pack(side="right")

        card = ttk.Frame(outer, padding=12, style="HubCard.TFrame")
        card.pack(fill="both", expand=True)
        ttk.Label(
            card,
            text="Recent Projects",
            background="#07111C",
            foreground="#62E5FF",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        self.recent_tree = ttk.Treeview(card, columns=("path",), show="tree headings")
        self.recent_tree.heading("#0", text="Project")
        self.recent_tree.heading("path", text="Location")
        self.recent_tree.column("#0", width=190, stretch=False)
        self.recent_tree.column("path", width=460, stretch=True)
        self.recent_tree.pack(fill="both", expand=True)
        self.recent_tree.bind("<Double-1>", lambda _event: self._open_selected_recent())

        footer = ttk.Frame(outer, style="Hub.TFrame")
        footer.pack(fill="x", pady=(14, 0))
        ttk.Button(
            footer,
            text="Open Selected",
            style="Hub.TButton",
            command=self._open_selected_recent,
        ).pack(side="right")
        ttk.Button(
            footer,
            text="Refresh",
            style="Hub.TButton",
            command=self._refresh_recent,
        ).pack(side="right", padx=(0, 8))

    def _refresh_recent(self) -> None:
        self.recent_tree.delete(*self.recent_tree.get_children())
        self._recent_by_iid.clear()
        for index, path in enumerate(self.hub.recent_projects()):
            iid = f"recent-{index}"
            try:
                name = ProjectManifest.load(path).name
            except (FileNotFoundError, ProjectManifestError):
                name = path.name
            self.recent_tree.insert("", "end", iid=iid, text=name, values=(str(path),))
            self._recent_by_iid[iid] = path

    def _new_project(self, mode: str) -> None:
        parent = self.filedialog.askdirectory(title="Choose project folder")
        if not parent:
            return
        name = self.simpledialog.askstring(
            "New SwirEngine Project",
            "Project name:",
            parent=self.root,
        )
        if name is None or not name.strip():
            return
        try:
            self.session = self.hub.create_project(name.strip(), mode, parent=parent)
        except (FileExistsError, OSError, ValueError, EditorProjectOpenError) as exc:
            self.messagebox.showerror(
                "SwirEditor — New project failed",
                str(exc),
                parent=self.root,
            )
            return
        self.root.destroy()

    def _open_project(self) -> None:
        path = self.filedialog.askdirectory(title="Open SwirEngine project")
        if path:
            self._open_path(Path(path))

    def _open_selected_recent(self) -> None:
        selection = self.recent_tree.selection()
        if not selection:
            return
        path = self._recent_by_iid.get(selection[0])
        if path is not None:
            self._open_path(path)

    def _open_path(self, path: Path) -> None:
        try:
            self.session = self.hub.open_project(path)
        except (OSError, ValueError, EditorProjectOpenError) as exc:
            self.messagebox.showerror("SwirEditor — Open failed", str(exc), parent=self.root)
            return
        self.root.destroy()
