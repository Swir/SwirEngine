from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .editor_lighting22 import EditorLightingPanelController22
from .editor_vfx_frontend22 import TkVFXEditorApp22
from .lighting_authoring22 import LightSpec22

_ENUMS = {"kind": ("directional", "point", "spot"), "tone_mapping": ("none", "reinhard", "aces")}
_SECTIONS = (
    ("Environment", "environment", None),
    ("Shadows", "renderer", ("cascaded_shadows", "shadow_cascades", "shadow_resolution",
                               "shadow_distance", "shadow_split_lambda", "shadow_overlap")),
    ("Effects", "renderer", ("hdr", "depth_prepass", "ssao", "ssao_radius", "ssao_power",
                              "ssao_samples", "bloom", "bloom_threshold", "bloom_intensity",
                              "bloom_levels", "decals", "max_decals")),
    ("Color grading", "postfx", None),
)


def _parse_field(value: Any, original: Any) -> Any:
    if isinstance(original, bool):
        if not isinstance(value, bool):
            raise ValueError("checkbox value must be boolean")
        return value
    if isinstance(original, tuple):
        return tuple(float(item.strip()) for item in str(value).split(","))
    if isinstance(original, int):
        return int(value)
    if isinstance(original, float):
        return float(value)
    if original is None:
        return str(value).strip() or None
    return str(value).strip()


class TkLightingEditorApp22(TkVFXEditorApp22):
    """Unified scene Lighting/Environment/Post-FX panel with isolated live rendering."""

    def __init__(self, controller: Any, *, lighting: Any, lighting_source: Any, **kwargs: Any) -> None:
        self.lighting_controller = EditorLightingPanelController22(lighting, lighting_source)
        self._lighting_window = None
        self._lighting_after = None
        self._lighting_fields: dict[str, dict[str, tuple[Any, Any]]] = {}
        self._lighting_photo = None
        self._lighting_scene_key = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        menu.add_command(label="Lighting / Environment / Post-FX…", command=self._open_lighting_editor)

    def _open_lighting_editor(self) -> None:
        if self._lighting_window is not None:
            self._lighting_window.deiconify()
            self._lighting_window.lift()
            return
        window = self.tk.Toplevel(self.root)
        self._lighting_window = window
        window.title("SwirEditor 2.2 — Lighting / Environment / Post-FX")
        window.geometry("1180x760")
        window.minsize(1060, 700)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_lighting_editor)
        window.columnconfigure(0, weight=1)
        window.columnconfigure(1, weight=1)
        window.rowconfigure(1, weight=1)
        self._lighting_scene_var = self.tk.StringVar()
        self.ttk.Label(window, textvariable=self._lighting_scene_var, padding=12).grid(
            row=0, column=0, columnspan=2, sticky="ew")
        self._lighting_notebook = self.ttk.Notebook(window)
        self._lighting_notebook.grid(row=1, column=0, sticky="nsew", padx=(12, 6))
        preview = self.ttk.Frame(window, padding=12)
        preview.grid(row=1, column=1, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(2, weight=1)
        toolbar = self.ttk.Frame(preview)
        toolbar.grid(row=0, column=0, sticky="ew")
        for label, command in (("Start / refresh scene", self._lighting_start),
                               ("Pause", self._lighting_pause), ("Step", self._lighting_step),
                               ("Stop", self._lighting_stop)):
            self.ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 4))
        self.ttk.Label(preview, text="Isolated active-scene snapshot • bounded 10 Hz preview",
                       wraplength=460).grid(row=1, column=0, sticky="w", pady=10)
        self._lighting_image = self.ttk.Label(preview, anchor="center", text="Start preview to render")
        self._lighting_image.grid(row=2, column=0, sticky="nsew")
        self.ttk.Label(preview, text="Apply updates lighting live. Refresh scene after geometry edits.\n"
                       "Preview never changes the original scene or its renderer settings.",
                       wraplength=460).grid(row=3, column=0, sticky="w", pady=10)
        self.ttk.Button(preview, text="Save lighting profiles", command=self._lighting_save).grid(
            row=4, column=0, sticky="ew")
        self._lighting_status = self.tk.StringVar(value=self.lighting_controller.status)
        self.ttk.Label(window, textvariable=self._lighting_status, padding=12,
                       wraplength=1000).grid(row=2, column=0, columnspan=2, sticky="ew")
        try:
            self._populate_lighting()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._lighting_error(exc)
        self._schedule_lighting()

    def _form(self, tab: Any, values: dict[str, Any], *, start: int = 0) -> dict[str, tuple[Any, Any]]:
        fields = {}
        tab.columnconfigure(1, weight=1)
        for row, (key, value) in enumerate(values.items(), start=start):
            self.ttk.Label(tab, text=key.replace("_", " ").title()).grid(
                row=row, column=0, sticky="w", padx=8, pady=4)
            if isinstance(value, bool):
                variable = self.tk.BooleanVar(value=value)
                widget = self.ttk.Checkbutton(tab, variable=variable)
            else:
                display = ", ".join(str(item) for item in value) if isinstance(value, tuple) else value
                variable = self.tk.StringVar(value="" if display is None else str(display))
                widget = (self.ttk.Combobox(tab, textvariable=variable, values=_ENUMS[key],
                                          state="readonly", width=24)
                          if key in _ENUMS else self.ttk.Entry(tab, textvariable=variable, width=24))
            widget.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            fields[key] = (variable, value)
        return fields

    def _populate_lighting(self, *, selected_light: str | None = None) -> None:
        spec = self.lighting_controller.spec()
        binding = (spec.scene, id(self.lighting_controller.source().scene), spec.mode)
        previous = getattr(self, "_lighting_light_list", None)
        if (selected_light is None and self._lighting_scene_key == binding
                and previous is not None and previous.winfo_exists()):
            selection = previous.curselection()
            if selection:
                selected_light = previous.get(selection[0])
        self._lighting_scene_key = binding
        self._lighting_scene_var.set(f"Active scene: {spec.scene}  |  {spec.mode.upper()}")
        for tab in self._lighting_notebook.tabs():
            self._lighting_notebook.nametowidget(tab).destroy()
        self._lighting_fields = {}
        light_tab = self.ttk.Frame(self._lighting_notebook, padding=6)
        self._lighting_notebook.add(light_tab, text="Lights")
        self._lighting_light_list = self.tk.Listbox(light_tab, height=4, exportselection=False)
        self._lighting_light_list.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        self._lighting_light_list.bind("<<ListboxSelect>>", self._lighting_select_light)
        for item in spec.lights:
            self._lighting_light_list.insert("end", item.name)
        selected = next((light for light in spec.lights if light.name == selected_light),
                        spec.lights[0] if spec.lights else LightSpec22("sun"))
        self._lighting_fields["light"] = self._form(light_tab, asdict(selected), start=1)
        if spec.lights:
            self._lighting_light_list.selection_set(spec.lights.index(selected))
        actions = self.ttk.Frame(light_tab)
        actions.grid(row=12, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        state = "normal" if spec.mode == "3d" else "disabled"
        self.ttk.Button(actions, text="Add / update light", state=state,
                        command=self._lighting_apply_light).pack(side="left", padx=(0, 8))
        self.ttk.Button(actions, text="Remove selected", state=state,
                        command=self._lighting_remove_light).pack(side="left")
        for title, section, names in _SECTIONS:
            tab = self.ttk.Frame(self._lighting_notebook, padding=6)
            self._lighting_notebook.add(tab, text=title)
            values = asdict(getattr(spec, section))
            if names is not None:
                values = {name: values[name] for name in names}
            self._lighting_fields[title] = self._form(tab, values)
            enabled = "normal" if spec.mode == "3d" or section == "postfx" else "disabled"
            self.ttk.Button(tab, text="Apply to active scene profile", state=enabled,
                            command=lambda s=section, t=title: self._lighting_apply(s, t)).grid(
                row=len(values), column=0, columnspan=2, sticky="ew", padx=8, pady=12)

    def _require_lighting_form_scene(self) -> None:
        source = self.lighting_controller.source()
        if self._lighting_scene_key != (source.key, id(source.scene), source.mode):
            self.lighting_controller.sync_scene()
            self._clear_lighting_image()
            self._populate_lighting()
            raise ValueError("Active scene changed; review its lighting controls before applying")

    def _lighting_values(self, group: str) -> dict[str, Any]:
        self._require_lighting_form_scene()
        return {key: _parse_field(variable.get(), None if key == "skybox_texture" else default)
                for key, (variable, default) in self._lighting_fields[group].items()}

    def _lighting_apply(self, section: str, group: str) -> None:
        self._lighting_action(lambda: self.lighting_controller.update_section(
            section, **self._lighting_values(group)))

    def _lighting_select_light(self, _event: Any = None) -> None:
        selected = self._lighting_light_list.curselection()
        if not selected:
            return
        name = self._lighting_light_list.get(selected[0])
        light = next((item for item in self.lighting_controller.spec().lights if item.name == name), None)
        if light is None:
            self._populate_lighting()
            return
        for key, value in asdict(light).items():
            variable, _ = self._lighting_fields["light"][key]
            variable.set(", ".join(str(item) for item in value) if isinstance(value, tuple) else value)

    def _lighting_apply_light(self) -> None:
        def apply() -> None:
            light = LightSpec22(**self._lighting_values("light"))
            self.lighting_controller.set_light(light)
            self._populate_lighting(selected_light=light.name)
        self._lighting_action(apply)

    def _lighting_remove_light(self) -> None:
        def remove() -> None:
            self._require_lighting_form_scene()
            selection = self._lighting_light_list.curselection()
            if not selection:
                raise ValueError("Select a light to remove")
            self.lighting_controller.remove_light(self._lighting_light_list.get(selection[0]))
            self._populate_lighting()
        self._lighting_action(remove)

    def _lighting_start(self) -> None:
        self._lighting_action(self.lighting_controller.start)

    def _lighting_pause(self) -> None:
        self._lighting_action(self.lighting_controller.pause)

    def _lighting_step(self) -> None:
        self._lighting_action(lambda: self._capture_lighting(step=True))

    def _lighting_stop(self) -> None:
        self._lighting_action(self.lighting_controller.stop)
        self._clear_lighting_image()

    def _lighting_save(self) -> None:
        self._lighting_action(self.lighting_controller.save)

    def _lighting_action(self, action: Any) -> None:
        try:
            action()
            self._lighting_status.set(self.lighting_controller.status)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._lighting_error(exc)

    def _lighting_error(self, exc: Exception) -> None:
        self._lighting_status.set(str(exc))
        self.controller.console.write(str(exc), level="error", source="lighting")

    def _clear_lighting_image(self) -> None:
        self._lighting_photo = None
        self._lighting_image.configure(image="", text="Preview stopped; original scene unchanged")

    def _capture_lighting(self, *, step: bool = False) -> None:
        # Fixed bounded target prevents layout feedback and framebuffer reallocations on every tick.
        image = self.lighting_controller.capture(480, 320, step=step)
        if image is not None:
            self._lighting_photo = self.tk.PhotoImage(
                master=self.root, data=image.to_ppm(), format="PPM")
            self._lighting_image.configure(image=self._lighting_photo, text="")

    def _schedule_lighting(self) -> None:
        if self._lighting_after is None and self._lighting_window is not None:
            self._lighting_after = self.root.after(100, self._lighting_tick)

    def _lighting_tick(self) -> None:
        self._lighting_after = None
        if self._lighting_window is None:
            return
        try:
            self.lighting_controller.sync_scene()
            source = self.lighting_controller.source()
            if self._lighting_scene_key != (source.key, id(source.scene), source.mode):
                self._clear_lighting_image()
                self._populate_lighting()
            if self.lighting_controller.active:
                self._capture_lighting()
            self._lighting_status.set(self.lighting_controller.status)
        except Exception as exc:  # noqa: BLE001 - keep Tk alive and remove invalid live preview
            self.lighting_controller.stop()
            self._clear_lighting_image()
            self._lighting_error(exc)
        self._schedule_lighting()

    def _close_lighting_editor(self) -> None:
        if self._lighting_after is not None:
            self.root.after_cancel(self._lighting_after)
            self._lighting_after = None
        try:
            self.lighting_controller.stop()
        finally:
            if self._lighting_window is not None:
                self._lighting_window.destroy()
                self._lighting_window = None
            self._lighting_photo = None

    def close(self) -> None:
        self._close_lighting_editor()
        super().close()
