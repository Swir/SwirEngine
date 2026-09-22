from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .editor_navigation_tooling21 import (
    EditorNavigationTooling21,
    EditorNavigationToolingError,
)
from .editor_physics_frontend21 import TkPhysicsEditorApp21
from .editor_viewport_frontend21 import EditorProductionViewportController21
from .navigation15 import NavigationQueryResult


@dataclass(frozen=True, slots=True)
class NavigationNodeRow21:
    name: str
    position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class NavigationEdgeRow21:
    name: str
    source: str
    target: str
    cost: float | None
    area: str
    bidirectional: bool
    enabled: bool


@dataclass(frozen=True, slots=True)
class NavigationAgentRow21:
    name: str
    position: tuple[float, float, float]
    radius: float
    max_speed: float


@dataclass(frozen=True, slots=True)
class NavigationPanelFrame21:
    path: str
    dirty: bool
    nodes: tuple[NavigationNodeRow21, ...]
    edges: tuple[NavigationEdgeRow21, ...]
    agents: tuple[NavigationAgentRow21, ...]
    preview_start: str | None
    preview_goal: str | None
    preview_node_ids: tuple[str, ...]


class EditorNavigationPanelController21:
    """Toolkit-neutral creator adapter over runtime-backed navigation authoring."""

    def __init__(self, tooling: EditorNavigationTooling21) -> None:
        if not isinstance(tooling, EditorNavigationTooling21):
            raise TypeError("tooling must be an EditorNavigationTooling21")
        self.tooling = tooling
        self._preview_start: str | None = None
        self._preview_goal: str | None = None
        self._preview_node_ids: tuple[str, ...] = ()
        self._status = "Navigation tooling ready"

    @property
    def status(self) -> str:
        return self._status

    def frame(self) -> NavigationPanelFrame21:
        snapshot = self.tooling.snapshot()
        return NavigationPanelFrame21(
            path=snapshot.path,
            dirty=snapshot.dirty,
            nodes=tuple(NavigationNodeRow21(node.name, node.position) for node in snapshot.nodes),
            edges=tuple(
                NavigationEdgeRow21(
                    edge.name,
                    edge.source,
                    edge.target,
                    edge.cost,
                    edge.area,
                    edge.bidirectional,
                    edge.enabled,
                )
                for edge in snapshot.edges
            ),
            agents=tuple(
                NavigationAgentRow21(
                    agent.name,
                    agent.position,
                    agent.radius,
                    agent.max_speed,
                )
                for agent in snapshot.agents
            ),
            preview_start=self._preview_start,
            preview_goal=self._preview_goal,
            preview_node_ids=self._preview_node_ids,
        )

    def create_node(self, name: str, position: tuple[float, float, float]) -> NavigationPanelFrame21:
        self.tooling.create_node(name, position)
        self._clear_preview()
        self._status = f"Created navigation node {name}"
        return self.frame()

    def update_node(self, name: str, position: tuple[float, float, float]) -> NavigationPanelFrame21:
        self.tooling.update_node(name, position)
        self._clear_preview()
        self._status = f"Updated navigation node {name}"
        return self.frame()

    def rename_node(self, name: str, new_name: str) -> NavigationPanelFrame21:
        self.tooling.rename_node(name, new_name)
        self._clear_preview()
        self._status = f"Renamed navigation node {name} to {new_name}"
        return self.frame()

    def remove_node(self, name: str) -> NavigationPanelFrame21:
        self.tooling.remove_node(name)
        self._clear_preview()
        self._status = f"Removed navigation node {name}"
        return self.frame()

    def create_edge(
        self,
        name: str,
        source: str,
        target: str,
        *,
        area: str = "default",
        cost: float | None = None,
        bidirectional: bool = True,
        enabled: bool = True,
    ) -> NavigationPanelFrame21:
        self.tooling.create_edge(
            name,
            source,
            target,
            area=area,
            cost=cost,
            bidirectional=bidirectional,
            enabled=enabled,
        )
        self._clear_preview()
        self._status = f"Created navigation edge {name}"
        return self.frame()

    def remove_edge(self, name: str) -> NavigationPanelFrame21:
        self.tooling.remove_edge(name)
        self._clear_preview()
        self._status = f"Removed navigation edge {name}"
        return self.frame()

    def create_agent(
        self,
        name: str,
        position: tuple[float, float, float],
        **settings: Any,
    ) -> NavigationPanelFrame21:
        self.tooling.create_agent(name, position, **settings)
        self._status = f"Created navigation agent {name}"
        return self.frame()

    def update_agent(self, name: str, **changes: Any) -> NavigationPanelFrame21:
        self.tooling.update_agent(name, **changes)
        self._status = f"Updated navigation agent {name}"
        return self.frame()

    def remove_agent(self, name: str) -> NavigationPanelFrame21:
        self.tooling.remove_agent(name)
        self._status = f"Removed navigation agent {name}"
        return self.frame()

    def preview_nodes(self, start: str, goal: str) -> tuple[NavigationPanelFrame21, NavigationQueryResult]:
        snapshot = self.tooling.snapshot()
        positions = {node.name: node.position for node in snapshot.nodes}
        try:
            start_position = positions[start]
            goal_position = positions[goal]
        except KeyError as exc:
            raise EditorNavigationToolingError(f"unknown navigation node {exc.args[0]!r}") from exc
        result = self.tooling.preview_path(start_position, goal_position)
        self._preview_start = start
        self._preview_goal = goal
        self._preview_node_ids = () if result.path is None else tuple(result.path.node_ids)
        self._status = f"Previewed navigation path {start} → {goal}"
        return self.frame(), result

    def save(self) -> NavigationPanelFrame21:
        snapshot = self.tooling.save()
        self._status = f"Saved navigation configuration {snapshot.path}"
        return self.frame()

    def reload(self) -> NavigationPanelFrame21:
        self.tooling.load()
        self._clear_preview()
        self._status = "Reloaded saved navigation configuration"
        return self.frame()

    def _clear_preview(self) -> None:
        self._preview_start = None
        self._preview_goal = None
        self._preview_node_ids = ()


def parse_navigation_point21(text: str) -> tuple[float, float, float]:
    """Parse a portable x,y,z point from the desktop navigation panel."""

    parts = tuple(part.strip() for part in str(text).split(",") if part.strip())
    if len(parts) != 3:
        raise ValueError("position must contain exactly three comma-separated numbers")
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError as exc:
        raise ValueError("position must contain exactly three comma-separated numbers") from exc


class TkNavigationEditorApp21(TkPhysicsEditorApp21):
    """Production SwirEditor shell with integrated navigation/AI authoring."""

    controller: EditorProductionViewportController21

    def __init__(
        self,
        controller: EditorProductionViewportController21,
        *,
        navigation: EditorNavigationTooling21,
        **kwargs: Any,
    ) -> None:
        self.navigation_controller = EditorNavigationPanelController21(navigation)
        self._navigation_window: Any | None = None
        self._navigation_nodes_tree: Any | None = None
        self._navigation_edges_tree: Any | None = None
        self._navigation_agents_tree: Any | None = None
        self._navigation_status_var: Any | None = None
        self._navigation_preview_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        navigation = self.tk.Menu(menu, tearoff=False)
        navigation.add_command(label="Graph & Agents…", command=self._open_navigation_panel)
        menu.add_cascade(label="Navigation", menu=navigation)

    def _open_navigation_panel(self) -> None:
        if self._navigation_window is not None and self._navigation_window.winfo_exists():
            self._navigation_window.deiconify()
            self._navigation_window.lift()
            self._navigation_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor — Navigation & AI")
        window.geometry("1040x760")
        window.minsize(840, 560)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_navigation_panel)
        self._navigation_window = window

        notebook = self.ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        self._navigation_nodes_tree = self._build_navigation_tree(
            notebook,
            "Nodes",
            (("name", "Name", 180), ("position", "Position", 320)),
        )
        self._navigation_edges_tree = self._build_navigation_tree(
            notebook,
            "Edges",
            (
                ("name", "Name", 160),
                ("source", "Source", 150),
                ("target", "Target", 150),
                ("area", "Area", 110),
                ("cost", "Cost", 80),
            ),
        )
        self._navigation_agents_tree = self._build_navigation_tree(
            notebook,
            "Agents",
            (
                ("name", "Name", 180),
                ("position", "Position", 300),
                ("radius", "Radius", 90),
                ("speed", "Max speed", 100),
            ),
        )

        actions = self.ttk.Frame(window, padding=(12, 0, 12, 8))
        actions.pack(fill="x")
        for label, command in (
            ("Add Node…", self._navigation_add_node),
            ("Add Edge…", self._navigation_add_edge),
            ("Add Agent…", self._navigation_add_agent),
            ("Remove", self._navigation_remove_selected),
            ("Path Preview…", self._navigation_preview),
            ("Save", self._navigation_save),
            ("Reload", self._navigation_reload),
        ):
            self.ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6))

        preview = self.ttk.LabelFrame(window, text="Runtime-backed path preview", padding=8)
        preview.pack(fill="x", padx=12, pady=(0, 8))
        self._navigation_preview_var = self.tk.StringVar(value="No path preview")
        self.ttk.Label(preview, textvariable=self._navigation_preview_var).pack(
            side="left", fill="x", expand=True
        )

        footer = self.ttk.Frame(window, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        self._navigation_status_var = self.tk.StringVar()
        self.ttk.Label(footer, textvariable=self._navigation_status_var).pack(side="left")
        self.ttk.Button(footer, text="Close", command=self._close_navigation_panel).pack(side="right")
        self._refresh_navigation_panel()

    def _build_navigation_tree(
        self,
        notebook: Any,
        title: str,
        columns: tuple[tuple[str, str, int], ...],
    ) -> Any:
        frame = self.ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=title)
        keys = tuple(column[0] for column in columns)
        tree = self.ttk.Treeview(frame, columns=keys, show="headings", selectmode="browse")
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key in {"name", "position"})
        tree.pack(fill="both", expand=True)
        return tree

    def _refresh_navigation_panel(self) -> None:
        frame = self.navigation_controller.frame()
        self._replace_tree_rows(
            self._navigation_nodes_tree,
            ((row.name, _format_point(row.position)) for row in frame.nodes),
            "navigation-node",
        )
        self._replace_tree_rows(
            self._navigation_edges_tree,
            (
                (
                    row.name,
                    row.source,
                    row.target,
                    row.area,
                    "auto" if row.cost is None else f"{row.cost:g}",
                )
                for row in frame.edges
            ),
            "navigation-edge",
        )
        self._replace_tree_rows(
            self._navigation_agents_tree,
            (
                (row.name, _format_point(row.position), f"{row.radius:g}", f"{row.max_speed:g}")
                for row in frame.agents
            ),
            "navigation-agent",
        )
        if self._navigation_preview_var is not None:
            if not frame.preview_node_ids:
                self._navigation_preview_var.set("No path preview")
            else:
                self._navigation_preview_var.set(" → ".join(frame.preview_node_ids))
        if self._navigation_status_var is not None:
            dirty = " · unsaved" if frame.dirty else ""
            self._navigation_status_var.set(self.navigation_controller.status + dirty)

    @staticmethod
    def _replace_tree_rows(tree: Any | None, rows: Any, prefix: str) -> None:
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for index, values in enumerate(rows):
            tree.insert("", "end", iid=f"{prefix}-{index}", values=values)

    def _navigation_add_node(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add navigation node", "Name:", parent=self._navigation_window)
        if not name:
            return
        point = simpledialog.askstring(
            "Add navigation node",
            "Position x, y, z:",
            initialvalue="0, 0, 0",
            parent=self._navigation_window,
        )
        if not point:
            return
        self._navigation_action(lambda: self.navigation_controller.create_node(name, parse_navigation_point21(point)))

    def _navigation_add_edge(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add navigation edge", "Name:", parent=self._navigation_window)
        if not name:
            return
        source = simpledialog.askstring("Add navigation edge", "Source node:", parent=self._navigation_window)
        if not source:
            return
        target = simpledialog.askstring("Add navigation edge", "Target node:", parent=self._navigation_window)
        if not target:
            return
        area = simpledialog.askstring(
            "Add navigation edge", "Area:", initialvalue="default", parent=self._navigation_window
        )
        if not area:
            return
        self._navigation_action(
            lambda: self.navigation_controller.create_edge(name, source, target, area=area)
        )

    def _navigation_add_agent(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring("Add navigation agent", "Name:", parent=self._navigation_window)
        if not name:
            return
        point = simpledialog.askstring(
            "Add navigation agent",
            "Position x, y, z:",
            initialvalue="0, 0, 0",
            parent=self._navigation_window,
        )
        if not point:
            return
        speed = simpledialog.askfloat(
            "Add navigation agent",
            "Maximum speed:",
            initialvalue=4.0,
            minvalue=0.0,
            parent=self._navigation_window,
        )
        if speed is None:
            return
        self._navigation_action(
            lambda: self.navigation_controller.create_agent(
                name, parse_navigation_point21(point), max_speed=speed
            )
        )

    def _navigation_remove_selected(self) -> None:
        selected = self._selected_navigation_item()
        if selected is None:
            return
        kind, name = selected
        if not self.messagebox.askyesno(
            "Remove navigation item", f"Remove {kind} {name}?", parent=self._navigation_window
        ):
            return
        if kind == "node":
            action = lambda: self.navigation_controller.remove_node(name)
        elif kind == "edge":
            action = lambda: self.navigation_controller.remove_edge(name)
        else:
            action = lambda: self.navigation_controller.remove_agent(name)
        self._navigation_action(action)

    def _selected_navigation_item(self) -> tuple[str, str] | None:
        for kind, tree in (
            ("node", self._navigation_nodes_tree),
            ("edge", self._navigation_edges_tree),
            ("agent", self._navigation_agents_tree),
        ):
            if tree is None:
                continue
            selection = tree.selection()
            if selection:
                values = tree.item(selection[0], "values")
                if values:
                    return kind, str(values[0])
        return None

    def _navigation_preview(self) -> None:
        from tkinter import simpledialog

        frame = self.navigation_controller.frame()
        if len(frame.nodes) < 2:
            self.messagebox.showinfo(
                "SwirEditor — Navigation", "Create at least two nodes first.", parent=self._navigation_window
            )
            return
        start = simpledialog.askstring(
            "Navigation path preview",
            "Start node:",
            initialvalue=frame.nodes[0].name,
            parent=self._navigation_window,
        )
        if not start:
            return
        goal = simpledialog.askstring(
            "Navigation path preview",
            "Goal node:",
            initialvalue=frame.nodes[-1].name,
            parent=self._navigation_window,
        )
        if not goal:
            return
        self._navigation_action(lambda: self.navigation_controller.preview_nodes(start, goal))

    def _navigation_save(self) -> None:
        self._navigation_action(self.navigation_controller.save)

    def _navigation_reload(self) -> None:
        self._navigation_action(self.navigation_controller.reload)

    def _navigation_action(self, action: Any) -> None:
        try:
            action()
        except (EditorNavigationToolingError, TypeError, ValueError) as exc:
            self.messagebox.showerror(
                "SwirEditor — Navigation", str(exc), parent=self._navigation_window
            )
            return
        self._refresh_navigation_panel()

    def _close_navigation_panel(self) -> None:
        window, self._navigation_window = self._navigation_window, None
        self._navigation_nodes_tree = None
        self._navigation_edges_tree = None
        self._navigation_agents_tree = None
        self._navigation_status_var = None
        self._navigation_preview_var = None
        if window is not None and window.winfo_exists():
            window.destroy()


def _format_point(point: tuple[float, float, float]) -> str:
    return ", ".join(f"{value:g}" for value in point)
