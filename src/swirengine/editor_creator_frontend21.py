from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import PurePath
from typing import Any

from .ecs import Entity
from .editor_assets import EditorAssetBrowser
from .editor_diagnostics import EditorConsole, EditorProfiler
from .editor_frontend import EditorFrontendController, EditorFrontendFrame, TkEditorApp
from .editor_preview import EditorPreviewSession
from .editor_project_authoring21 import EditorProjectAuthoring21
from .editor_workspace import EditorWorkspace

ComponentFactory = Callable[[], object]
_MIXED = "<mixed>"


@dataclass(frozen=True, slots=True)
class CreatorInspectorRow:
    name: str
    value: object
    display_value: str
    type_name: str
    editable: bool
    kind: str
    mixed: bool = False
    choices: tuple[str, ...] = ()


class EditorCreatorFrontendController21(EditorFrontendController):
    """Bind the active desktop front-end to project-aware 2.1 authoring."""

    def __init__(
        self,
        workspace: EditorWorkspace,
        authoring: EditorProjectAuthoring21,
        *,
        asset_browser: EditorAssetBrowser | None = None,
        console: EditorConsole | None = None,
        profiler: EditorProfiler | None = None,
        preview: EditorPreviewSession | None = None,
        component_factories: Mapping[str, ComponentFactory] | None = None,
    ) -> None:
        if not isinstance(authoring, EditorProjectAuthoring21):
            raise TypeError("authoring must be an EditorProjectAuthoring21")
        if authoring.workspace is not workspace:
            raise ValueError("authoring workspace must match controller workspace")
        super().__init__(
            workspace,
            asset_browser=asset_browser,
            console=console,
            profiler=profiler,
            preview=preview,
        )
        self.authoring = authoring
        self._component_factories = dict(component_factories or {})
        self._factory_component_types: dict[str, type[object]] = {
            name: factory
            for name, factory in self._component_factories.items()
            if isinstance(factory, type)
        }

    @property
    def selection_count(self) -> int:
        return self.authoring.components.selection_snapshot.count

    def frame(self) -> EditorFrontendFrame:
        base = super().frame()
        creator = self.authoring.frame()
        selected = set(creator.selection.keys)
        hierarchy = tuple(replace(row, selected=row.key in selected) for row in base.hierarchy)
        fields = tuple(
            CreatorInspectorRow(
                field.name,
                field.value,
                self._display_typed_value(field.value, field.kind, field.mixed),
                field.type_name,
                field.editable,
                field.kind,
                field.mixed,
                field.choices,
            )
            for field in creator.fields
        )
        components = self.authoring.components
        shell = replace(
            base.shell,
            can_undo=bool(components.creator_undo_history) or base.shell.can_undo,
            can_redo=bool(components.creator_redo_history) or base.shell.can_redo,
        )
        return replace(base, shell=shell, hierarchy=hierarchy, inspector_fields=fields)

    def select(self, key: str | None) -> object | None:
        if key is None:
            self.authoring.clear_selection()
            self._status = "Selection cleared"
            return None
        self.authoring.select(key, mode="replace")
        self._status = f"Selected {key}"
        return self.workspace.inspector.resolve(key)

    def select_many(
        self,
        keys: tuple[str, ...] | list[str],
        *,
        primary_key: str | None = None,
    ) -> tuple[str, ...]:
        ordered = list(dict.fromkeys(keys))
        if primary_key is not None and primary_key in ordered:
            ordered.remove(primary_key)
            ordered.append(primary_key)
        if not ordered:
            self.authoring.clear_selection()
            self._status = "Selection cleared"
            return ()
        snapshot = self.authoring.select_many(ordered, replace=True)
        self._status = f"Selected {snapshot.count} item(s)"
        return snapshot.keys

    def edit_property(self, name: str, text: str) -> object:
        result = self.authoring.set_typed_property(name, text)
        self._status = f"Changed {name} on {len(result.target_keys)} item(s)"
        return result.value if hasattr(result, "value") else result.relative_path

    def undo(self) -> bool:
        edit = self.authoring.undo()
        self._status = "Undo" if edit is not None else "Nothing to undo"
        return edit is not None

    def redo(self) -> bool:
        edit = self.authoring.redo()
        self._status = "Redo" if edit is not None else "Nothing to redo"
        return edit is not None

    def available_add_component_names(self) -> tuple[str, ...]:
        entities = self._selected_entities()
        if not entities:
            return ()
        existing_types = {type(component) for entity in entities for component in entity.components}
        catalog = self._component_catalog()
        names = {
            name
            for name, component_type in catalog.items()
            if component_type not in existing_types
            and (name in self._component_factories or self._supports_no_arg(component_type))
        }
        names.update(name for name in self._component_factories if name not in catalog)
        return tuple(sorted(names))

    def available_remove_component_names(self) -> tuple[str, ...]:
        entities = self._selected_entities()
        if not entities:
            return ()
        common = {type(component) for component in entities[0].components}
        for entity in entities[1:]:
            common.intersection_update(type(component) for component in entity.components)
        return tuple(sorted(self._component_name(component_type) for component_type in common))

    def add_component_by_name(self, name: str) -> object:
        if name in self._component_factories:
            component = self._component_factories[name]()
            component_type = type(component)
            known_type = self._factory_component_types.get(name)
            if known_type is not None and known_type is not component_type:
                raise TypeError(
                    f"component factory {name!r} returned {component_type.__name__}; "
                    f"expected {known_type.__name__}"
                )
            self._factory_component_types[name] = component_type
        else:
            catalog = self._component_catalog()
            try:
                component_type = catalog[name]
            except KeyError as exc:
                raise KeyError(f"unknown component type {name!r}") from exc
            if not self._supports_no_arg(component_type):
                raise TypeError(f"component {name!r} requires constructor arguments")
            component = component_type()
        result = self.authoring.add_component(component)
        self._status = f"Added {type(component).__name__} to {len(result.target_keys)} entity(s)"
        return result

    def remove_component_by_name(self, name: str) -> object:
        catalog = self._component_catalog()
        try:
            component_type = catalog[name]
        except KeyError as exc:
            raise KeyError(f"unknown component type {name!r}") from exc
        result = self.authoring.remove_component(component_type)
        self._status = f"Removed {component_type.__name__} from {len(result.target_keys)} entity(s)"
        return result

    def create_prefab(
        self,
        asset_id: str,
        *,
        relative_path: str | PurePath | None = None,
    ) -> object:
        asset = self.authoring.create_prefab(asset_id, relative_path=relative_path)
        self._status = f"Created prefab {asset.asset_id}"
        return asset

    def load_prefab(self, asset_id: str, relative_path: str | PurePath) -> object:
        asset = self.authoring.load_prefab(asset_id, relative_path)
        self._status = f"Loaded prefab {asset.asset_id}"
        return asset

    def instantiate_prefab(self, asset_id: str) -> object:
        result = self.authoring.instantiate_prefab(asset_id)
        self._status = f"Instantiated prefab {asset_id} as {result.binding.binding_id}"
        return result

    def apply_prefab(self, binding_id: str) -> object:
        asset = self.authoring.apply_prefab(binding_id)
        self._status = f"Applied {binding_id} to prefab {asset.asset_id}"
        return asset

    def revert_prefab(self, binding_id: str) -> object:
        transaction = self.authoring.revert_prefab(binding_id)
        self._status = f"Reverted prefab instance {binding_id}"
        return transaction

    def prefab_asset_ids(self) -> tuple[str, ...]:
        return tuple(asset.asset_id for asset in self.authoring.frame().prefab_assets)

    def prefab_binding_ids(self) -> tuple[str, ...]:
        return tuple(binding.binding_id for binding in self.authoring.frame().prefab_bindings)

    def _selected_entities(self) -> tuple[Entity, ...]:
        targets = self.authoring.components.selected_targets
        if not targets or not all(isinstance(target, Entity) for target in targets):
            return ()
        return tuple(target for target in targets if isinstance(target, Entity))

    def _component_catalog(self) -> dict[str, type[object]]:
        catalog: dict[str, type[object]] = {}
        for entity in self.workspace.scene.entities:
            for component in entity.components:
                component_type = type(component)
                catalog[self._component_name(component_type)] = component_type
        catalog.update(self._factory_component_types)
        return catalog

    @staticmethod
    def _component_name(component_type: type[object]) -> str:
        return f"{component_type.__module__}.{component_type.__qualname__}"

    @staticmethod
    def _supports_no_arg(component_type: type[object]) -> bool:
        try:
            inspect.signature(component_type).bind()
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _display_typed_value(value: object, kind: str, mixed: bool) -> str:
        if mixed:
            return _MIXED
        if kind == "choice" and isinstance(value, Enum):
            return value.name
        if kind == "asset_path" and isinstance(value, PurePath):
            return value.as_posix()
        if kind == "tags" and isinstance(value, set):
            return ", ".join(sorted(str(item) for item in value))
        if isinstance(value, str):
            return value
        return repr(value)


class TkCreatorEditorApp21(TkEditorApp):
    """Desktop SwirEditor shell with 2.1 multi-selection and typed creator controls."""

    controller: EditorCreatorFrontendController21

    def __init__(self, controller: EditorCreatorFrontendController21, **kwargs: Any) -> None:
        self._field_vars: dict[str, Any] = {}
        super().__init__(controller, **kwargs)
        self.hierarchy_tree.configure(selectmode="extended")

    def install_creator_menu(self, menu: Any) -> None:
        creator = self.tk.Menu(menu, tearoff=False)
        creator.add_command(label="Add Component…", command=self._add_component)
        creator.add_command(label="Remove Component…", command=self._remove_component)
        creator.add_separator()
        creator.add_command(label="Create Prefab…", command=self._create_prefab)
        creator.add_command(label="Load Prefab…", command=self._load_prefab)
        creator.add_command(label="Instantiate Prefab…", command=self._instantiate_prefab)
        creator.add_command(label="Apply Prefab…", command=self._apply_prefab)
        creator.add_command(label="Revert Prefab…", command=self._revert_prefab)
        menu.add_cascade(label="Creator", menu=creator)

    def _refresh_hierarchy(self, frame: EditorFrontendFrame) -> None:
        selected = {row.key for row in frame.hierarchy if row.selected}
        self.hierarchy_tree.delete(*self.hierarchy_tree.get_children())
        self._hierarchy_keys.clear()
        parents: dict[str, str] = {}
        selected_iids: list[str] = []
        for index, row in enumerate(frame.shell.hierarchy):
            parent_iid = parents.get(row.parent_key, "") if row.parent_key is not None else ""
            iid = f"h{index}"
            marker = "" if row.enabled else " [disabled]"
            self.hierarchy_tree.insert(parent_iid, "end", iid=iid, text=f"{row.label}{marker}")
            self._hierarchy_keys[iid] = row.key
            parents[row.key] = iid
            if row.key in selected:
                selected_iids.append(iid)
        if selected_iids:
            self.hierarchy_tree.selection_set(selected_iids)
            primary = self.controller.authoring.components.selection_snapshot.primary_key
            primary_iid = next(
                (iid for iid, key in self._hierarchy_keys.items() if key == primary),
                selected_iids[-1],
            )
            self.hierarchy_tree.focus(primary_iid)
            self.hierarchy_tree.see(primary_iid)

    def _hierarchy_select(self, _event: object = None) -> None:
        iids = list(self.hierarchy_tree.selection())
        keys = [self._hierarchy_keys[iid] for iid in iids if iid in self._hierarchy_keys]
        focus = self.hierarchy_tree.focus()
        self.controller.select_many(keys, primary_key=self._hierarchy_keys.get(focus))

    def _refresh_inspector(self, frame: EditorFrontendFrame) -> None:
        for child in self.inspector_body.winfo_children():
            child.destroy()
        self._field_entries.clear()
        self._field_vars.clear()
        if frame.shell.inspector is None:
            self.ttk.Label(self.inspector_body, text="Nothing selected").grid(row=0, column=0)
            return
        count = self.controller.selection_count
        heading = frame.shell.inspector.type_name if count == 1 else f"{count} selected"
        self.ttk.Label(
            self.inspector_body,
            text=heading,
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        for row_index, field in enumerate(frame.inspector_fields, start=1):
            self.ttk.Label(self.inspector_body, text=field.name).grid(
                row=row_index, column=0, sticky="w", padx=(0, 6), pady=2
            )
            kind = getattr(field, "kind", "text")
            mixed = bool(getattr(field, "mixed", False))
            if kind == "boolean":
                variable = self.tk.StringVar(value="mixed" if mixed else str(bool(field.value)).lower())
                widget = self.ttk.Checkbutton(
                    self.inspector_body,
                    variable=variable,
                    onvalue="true",
                    offvalue="false",
                    command=lambda name=field.name, var=variable: self._commit_typed(name, var.get()),
                )
                if not field.editable:
                    widget.configure(state="disabled")
                self._field_vars[field.name] = variable
            elif kind == "choice":
                variable = self.tk.StringVar(value=field.display_value)
                values = tuple(getattr(field, "choices", ()))
                if mixed:
                    values = (_MIXED, *values)
                widget = self.ttk.Combobox(
                    self.inspector_body,
                    textvariable=variable,
                    values=values,
                    state="readonly" if field.editable else "disabled",
                )
                widget.bind(
                    "<<ComboboxSelected>>",
                    lambda _event, name=field.name, var=variable: self._commit_typed(name, var.get()),
                )
                self._field_vars[field.name] = variable
            else:
                widget = self.ttk.Entry(self.inspector_body)
                widget.insert(0, field.display_value)
                if not field.editable:
                    widget.configure(state="disabled")
                else:
                    widget.bind(
                        "<Return>",
                        lambda _event, name=field.name, entry=widget: self._commit_typed(name, entry.get()),
                    )
                    widget.bind(
                        "<FocusOut>",
                        lambda _event, name=field.name, entry=widget: self._commit_typed(name, entry.get()),
                    )
            widget.grid(row=row_index, column=1, sticky="ew", pady=2)
            self._field_entries[field.name] = widget
        self.inspector_body.columnconfigure(1, weight=1)

    def _commit_typed(self, name: str, value: str) -> None:
        if value == _MIXED:
            return
        try:
            self.controller.edit_property(name, value)
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))

    def _choose(self, title: str, prompt: str, choices: tuple[str, ...]) -> str | None:
        if not choices:
            self.messagebox.showinfo(title, "No compatible items are available.", parent=self.root)
            return None
        from tkinter import simpledialog

        value = simpledialog.askstring(
            title,
            f"{prompt}\n\nAvailable:\n" + "\n".join(choices),
            parent=self.root,
        )
        if value is None:
            return None
        clean = value.strip()
        if clean not in choices:
            self.messagebox.showerror(title, f"Unknown selection: {clean}", parent=self.root)
            return None
        return clean

    def _run_creator_action(self, title: str, action: Callable[[], object]) -> None:
        try:
            action()
        except (AttributeError, KeyError, LookupError, OSError, TypeError, ValueError, RuntimeError) as exc:
            self.status_var.set(str(exc))
            self.messagebox.showerror(title, str(exc), parent=self.root)

    def _add_component(self) -> None:
        name = self._choose(
            "Add Component",
            "Enter a component type name.",
            self.controller.available_add_component_names(),
        )
        if name is not None:
            self._run_creator_action("Add Component", lambda: self.controller.add_component_by_name(name))

    def _remove_component(self) -> None:
        name = self._choose(
            "Remove Component",
            "Enter a component type name.",
            self.controller.available_remove_component_names(),
        )
        if name is not None:
            self._run_creator_action(
                "Remove Component", lambda: self.controller.remove_component_by_name(name)
            )

    def _create_prefab(self) -> None:
        from tkinter import simpledialog

        asset_id = simpledialog.askstring("Create Prefab", "Prefab asset ID:", parent=self.root)
        if not asset_id:
            return
        clean_id = asset_id.strip()
        relative_path = simpledialog.askstring(
            "Create Prefab",
            "Project-relative prefab path:",
            initialvalue=f"prefabs/{clean_id}.swirprefab",
            parent=self.root,
        )
        if relative_path is not None:
            self._run_creator_action(
                "Create Prefab",
                lambda: self.controller.create_prefab(clean_id, relative_path=relative_path.strip()),
            )

    def _load_prefab(self) -> None:
        from tkinter import simpledialog

        asset_id = simpledialog.askstring("Load Prefab", "Prefab asset ID:", parent=self.root)
        if not asset_id:
            return
        relative_path = simpledialog.askstring(
            "Load Prefab", "Project-relative prefab path:", parent=self.root
        )
        if relative_path:
            self._run_creator_action(
                "Load Prefab",
                lambda: self.controller.load_prefab(asset_id.strip(), relative_path.strip()),
            )

    def _instantiate_prefab(self) -> None:
        asset_id = self._choose(
            "Instantiate Prefab", "Enter a prefab asset ID.", self.controller.prefab_asset_ids()
        )
        if asset_id is not None:
            self._run_creator_action(
                "Instantiate Prefab", lambda: self.controller.instantiate_prefab(asset_id)
            )

    def _apply_prefab(self) -> None:
        binding_id = self._choose(
            "Apply Prefab", "Enter a prefab binding ID.", self.controller.prefab_binding_ids()
        )
        if binding_id is not None:
            self._run_creator_action("Apply Prefab", lambda: self.controller.apply_prefab(binding_id))

    def _revert_prefab(self) -> None:
        binding_id = self._choose(
            "Revert Prefab", "Enter a prefab binding ID.", self.controller.prefab_binding_ids()
        )
        if binding_id is not None:
            self._run_creator_action(
                "Revert Prefab", lambda: self.controller.revert_prefab(binding_id)
            )
