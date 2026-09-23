from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .editor_material_frontend22 import TkMaterialEditorApp22
from .editor_visual_scripting22 import (
    EditorVisualScriptingError22,
    EditorVisualScriptingTooling22,
)
from .visual_scripting22 import NODE_TYPES_22, GraphExecutionContext22, GraphExecutionResult22


@dataclass(frozen=True, slots=True)
class VisualScriptEditorFrame22:
    selected: str | None
    graph_names: tuple[str, ...]
    node_count: int
    link_count: int
    dirty: bool
    diagnostics: tuple[str, ...] = ()


class EditorVisualScriptPanelController22:
    """Toolkit-neutral visual scripting controller used by SwirEditor."""

    def __init__(self, tooling: EditorVisualScriptingTooling22) -> None:
        if not isinstance(tooling, EditorVisualScriptingTooling22):
            raise TypeError("tooling must be EditorVisualScriptingTooling22")
        self.tooling = tooling
        names = tuple(graph.name for graph in tooling.snapshot().graphs)
        self._selected = names[0] if names else None
        self._status = "Visual Scripting / Node Graph ready"

    @property
    def status(self) -> str:
        return self._status

    @property
    def node_types(self) -> tuple[str, ...]:
        return tuple(sorted(NODE_TYPES_22))

    def frame(self) -> VisualScriptEditorFrame22:
        snapshot = self.tooling.snapshot()
        names = tuple(graph.name for graph in snapshot.graphs)
        if self._selected not in names:
            self._selected = names[0] if names else None
        if self._selected is None:
            return VisualScriptEditorFrame22(None, names, 0, 0, snapshot.dirty)
        graph = self.tooling.graph(self._selected)
        diagnostics = tuple(issue.message for issue in self.tooling.diagnostics(graph.name))
        return VisualScriptEditorFrame22(
            graph.name, names, len(graph.nodes), len(graph.links), snapshot.dirty, diagnostics
        )

    def selected_graph(self):
        if self._selected is None:
            raise EditorVisualScriptingError22("no node graph is selected")
        return self.tooling.graph(self._selected)

    def select(self, name: str) -> VisualScriptEditorFrame22:
        self.tooling.graph(name)
        self._selected = str(name).strip()
        self._status = f"Selected node graph {self._selected}"
        return self.frame()

    def create(self, name: str) -> VisualScriptEditorFrame22:
        graph = self.tooling.create_graph(name)
        self._selected = graph.name
        self.tooling.add_node(graph.name, "start", "event.start", x=40.0, y=100.0)
        self._status = f"Created node graph {graph.name}"
        return self.frame()

    def duplicate(self, new_name: str) -> VisualScriptEditorFrame22:
        graph = self.tooling.duplicate_graph(self.selected_graph().name, new_name)
        self._selected = graph.name
        self._status = f"Duplicated node graph as {graph.name}"
        return self.frame()

    def remove(self) -> VisualScriptEditorFrame22:
        name = self.selected_graph().name
        self.tooling.remove_graph(name)
        self._selected = None
        self._status = f"Removed node graph {name}"
        return self.frame()

    def add_node(
        self,
        node_id: str,
        kind: str,
        *,
        x: float = 100.0,
        y: float = 100.0,
        parameters: dict[str, object] | None = None,
    ) -> VisualScriptEditorFrame22:
        graph = self.selected_graph()
        self.tooling.add_node(
            graph.name, node_id, kind, x=x, y=y, parameters=parameters
        )
        self._status = f"Added {kind} node {node_id}"
        return self.frame()

    def update_parameters(
        self, node_id: str, parameters: dict[str, object]
    ) -> VisualScriptEditorFrame22:
        self.tooling.update_parameters(self.selected_graph().name, node_id, parameters)
        self._status = f"Updated parameters for {node_id}"
        return self.frame()

    def remove_node(self, node_id: str) -> VisualScriptEditorFrame22:
        self.tooling.remove_node(self.selected_graph().name, node_id)
        self._status = f"Removed node {node_id}"
        return self.frame()

    def connect(
        self, from_node: str, from_pin: str, to_node: str, to_pin: str
    ) -> VisualScriptEditorFrame22:
        self.tooling.connect(
            self.selected_graph().name, from_node, from_pin, to_node, to_pin
        )
        self._status = f"Connected {from_node}.{from_pin} → {to_node}.{to_pin}"
        return self.frame()

    def compile(self) -> VisualScriptEditorFrame22:
        graph = self.selected_graph()
        self.tooling.compile(graph.name)
        self._status = f"Compiled {graph.name} successfully"
        return self.frame()

    def run_preview(
        self,
        *,
        variables: dict[str, object] | None = None,
        max_steps: int = 256,
    ) -> GraphExecutionResult22:
        graph = self.selected_graph()
        context = GraphExecutionContext22(variables=dict(variables or {}))
        result = self.tooling.execute(graph.name, context, max_steps=max_steps)
        self._status = f"Preview executed {graph.name} in {result.steps} step(s)"
        return result

    def save(self) -> VisualScriptEditorFrame22:
        self.tooling.save()
        self._status = f"Saved node graphs to {self.tooling.relative_dir}"
        return self.frame()


class TkVisualScriptEditorApp22(TkMaterialEditorApp22):
    """SwirEditor shell with integrated visual node-graph authoring."""

    def __init__(
        self,
        controller: Any,
        *,
        visual_scripts: EditorVisualScriptingTooling22,
        **kwargs: Any,
    ) -> None:
        self.visual_script_controller = EditorVisualScriptPanelController22(visual_scripts)
        self._visual_window: Any | None = None
        self._visual_graph_list: Any | None = None
        self._visual_node_list: Any | None = None
        self._visual_canvas: Any | None = None
        self._visual_status_var: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        logic_menu = self.tk.Menu(menu, tearoff=False)
        logic_menu.add_command(
            label="Visual Scripting / Node Graph…",
            command=self._open_visual_scripting_editor,
        )
        menu.add_cascade(label="Logic", menu=logic_menu)

    def _open_visual_scripting_editor(self) -> None:
        if self._visual_window is not None and self._visual_window.winfo_exists():
            self._visual_window.deiconify()
            self._visual_window.lift()
            return
        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor 2.2 — Visual Scripting / Node Graph")
        window.geometry("1160x740")
        window.minsize(900, 600)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_visual_scripting_editor)
        self._visual_window = window

        body = self.ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = self.ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        self.ttk.Label(left, text="Graphs").pack(anchor="w")
        self._visual_graph_list = self.tk.Listbox(left, width=24, height=11, exportselection=False)
        self._visual_graph_list.pack(fill="x", pady=(4, 10))
        self._visual_graph_list.bind("<<ListboxSelect>>", self._visual_select_graph)
        self.ttk.Label(left, text="Nodes").pack(anchor="w")
        self._visual_node_list = self.tk.Listbox(left, width=24, height=19, exportselection=False)
        self._visual_node_list.pack(fill="both", expand=True, pady=(4, 0))

        right = self.ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self._visual_canvas = self.tk.Canvas(
            right, background="#11151c", highlightthickness=1, highlightbackground="#2f3a4a"
        )
        self._visual_canvas.grid(row=0, column=0, sticky="nsew")
        self._visual_status_var = self.tk.StringVar()
        self.ttk.Label(right, textvariable=self._visual_status_var, wraplength=820).grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )

        actions = self.ttk.Frame(body)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        commands = (
            ("New Graph", self._visual_new_graph),
            ("Add Node", self._visual_add_node),
            ("Node Params", self._visual_node_parameters),
            ("Remove Node", self._visual_remove_node),
            ("Connect", self._visual_connect),
            ("Compile", self._visual_compile),
            ("Run Preview", self._visual_run),
            ("Save", self._visual_save),
        )
        for index, (label, command) in enumerate(commands):
            self.ttk.Button(actions, text=label, command=command).grid(
                row=index // 4, column=index % 4, sticky="ew", padx=(0, 6), pady=(0, 6)
            )
        for column in range(4):
            actions.columnconfigure(column, weight=1)
        self._refresh_visual_scripting_editor()

    def _close_visual_scripting_editor(self) -> None:
        if self._visual_window is not None:
            self._visual_window.destroy()
        self._visual_window = None

    def _refresh_visual_scripting_editor(self) -> None:
        frame = self.visual_script_controller.frame()
        if self._visual_graph_list is not None:
            self._visual_graph_list.delete(0, self.tk.END)
            for index, name in enumerate(frame.graph_names):
                self._visual_graph_list.insert(self.tk.END, name)
                if name == frame.selected:
                    self._visual_graph_list.selection_set(index)
        graph = self.visual_script_controller.selected_graph() if frame.selected else None
        if self._visual_node_list is not None:
            self._visual_node_list.delete(0, self.tk.END)
            if graph is not None:
                for node in sorted(graph.nodes, key=lambda item: item.node_id):
                    self._visual_node_list.insert(self.tk.END, f"{node.node_id} · {node.kind}")
        if self._visual_status_var is not None:
            suffix = " · unsaved" if frame.dirty else ""
            diagnostic = f" · {frame.diagnostics[0]}" if frame.diagnostics else " · valid"
            self._visual_status_var.set(self.visual_script_controller.status + suffix + diagnostic)
        self._draw_graph(graph)

    def _draw_graph(self, graph: Any) -> None:
        canvas = self._visual_canvas
        if canvas is None:
            return
        canvas.delete("all")
        if graph is None:
            return
        positions = {node.node_id: (max(20.0, node.x), max(20.0, node.y)) for node in graph.nodes}
        for link in graph.links:
            source, target = positions.get(link.from_node), positions.get(link.to_node)
            if source and target:
                canvas.create_line(source[0] + 150, source[1] + 32, target[0], target[1] + 32, arrow=self.tk.LAST, width=2, fill="#6aa9ff")
        for node in sorted(graph.nodes, key=lambda item: item.node_id):
            x, y = positions[node.node_id]
            canvas.create_rectangle(x, y, x + 150, y + 64, fill="#1c2633", outline="#7fa9d9", width=2)
            label = NODE_TYPES_22[node.kind].label if node.kind in NODE_TYPES_22 else node.kind
            canvas.create_text(x + 8, y + 10, text=label, anchor="nw", fill="#ffffff")
            canvas.create_text(x + 8, y + 36, text=node.node_id, anchor="nw", fill="#b9c7d8")

    def _visual_select_graph(self, _event: object) -> None:
        selection = self._visual_graph_list.curselection() if self._visual_graph_list else ()
        if selection:
            self._visual_action(lambda: self.visual_script_controller.select(str(self._visual_graph_list.get(selection[0]))))

    def _selected_node_id(self) -> str | None:
        selection = self._visual_node_list.curselection() if self._visual_node_list else ()
        if not selection:
            return None
        return str(self._visual_node_list.get(selection[0])).split(" · ", 1)[0]

    def _visual_new_graph(self) -> None:
        from tkinter import simpledialog
        name = simpledialog.askstring("New node graph", "Graph name:", parent=self._visual_window)
        if name is not None:
            self._visual_action(lambda: self.visual_script_controller.create(name))

    def _visual_add_node(self) -> None:
        from tkinter import simpledialog
        node_id = simpledialog.askstring("Add node", "Node id:", parent=self._visual_window)
        if node_id is None:
            return
        kind = simpledialog.askstring(
            "Add node",
            "Node type:\n" + "\n".join(self.visual_script_controller.node_types),
            initialvalue="flow.end",
            parent=self._visual_window,
        )
        if kind is None:
            return
        text = simpledialog.askstring("Add node", "Parameters JSON object:", initialvalue="{}", parent=self._visual_window)
        if text is None:
            return
        try:
            params = json.loads(text)
            if not isinstance(params, dict):
                raise TypeError("node parameters must be a JSON object")
        except (json.JSONDecodeError, TypeError) as exc:
            self.messagebox.showerror("SwirEditor — Visual Scripting", str(exc), parent=self._visual_window)
            return
        count = len(self.visual_script_controller.selected_graph().nodes)
        self._visual_action(lambda: self.visual_script_controller.add_node(node_id, kind, x=210 + (count * 38) % 650, y=80 + (count // 8) * 110, parameters=params))

    def _visual_node_parameters(self) -> None:
        from tkinter import simpledialog
        node_id = self._selected_node_id()
        if node_id is None:
            return
        node = next(item for item in self.visual_script_controller.selected_graph().nodes if item.node_id == node_id)
        text = simpledialog.askstring("Node parameters", "Parameters JSON object:", initialvalue=json.dumps(dict(node.parameters), sort_keys=True), parent=self._visual_window)
        if text is None:
            return
        try:
            params = json.loads(text)
            if not isinstance(params, dict):
                raise TypeError("node parameters must be a JSON object")
        except (json.JSONDecodeError, TypeError) as exc:
            self.messagebox.showerror("SwirEditor — Visual Scripting", str(exc), parent=self._visual_window)
            return
        self._visual_action(lambda: self.visual_script_controller.update_parameters(node_id, params))

    def _visual_remove_node(self) -> None:
        node_id = self._selected_node_id()
        if node_id is not None:
            self._visual_action(lambda: self.visual_script_controller.remove_node(node_id))

    def _visual_connect(self) -> None:
        from tkinter import simpledialog
        text = simpledialog.askstring("Connect nodes", "source.pin -> target.pin", initialvalue="start.flow -> end.flow_in", parent=self._visual_window)
        if text is None:
            return
        try:
            left, right = (part.strip() for part in text.split("->", 1))
            from_node, from_pin = left.split(".", 1)
            to_node, to_pin = right.split(".", 1)
        except ValueError:
            self.messagebox.showerror("SwirEditor — Visual Scripting", "Use: source.pin -> target.pin", parent=self._visual_window)
            return
        self._visual_action(lambda: self.visual_script_controller.connect(from_node, from_pin, to_node, to_pin))

    def _visual_compile(self) -> None:
        self._visual_action(self.visual_script_controller.compile)

    def _visual_run(self) -> None:
        try:
            result = self.visual_script_controller.run_preview()
        except (EditorVisualScriptingError22, RuntimeError, TypeError, ValueError) as exc:
            self.messagebox.showerror("SwirEditor — Visual Scripting", str(exc), parent=self._visual_window)
            return
        emitted = ", ".join(f"{name}={value!r}" for name, value in result.emitted) or "none"
        self.messagebox.showinfo("Visual Script Preview", f"Steps: {result.steps}\nEmitted: {emitted}", parent=self._visual_window)
        self._refresh_visual_scripting_editor()

    def _visual_save(self) -> None:
        self._visual_action(self.visual_script_controller.save)

    def _visual_action(self, operation: Any) -> None:
        try:
            operation()
        except (EditorVisualScriptingError22, RuntimeError, TypeError, ValueError) as exc:
            self.messagebox.showerror("SwirEditor — Visual Scripting", str(exc), parent=self._visual_window)
        self._refresh_visual_scripting_editor()
