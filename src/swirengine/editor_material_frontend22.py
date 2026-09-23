from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from .core.scene import Scene
from .editor_build_export_frontend21 import TkBuildExportEditorApp21
from .editor_material_tooling22 import (
    DefineValue22,
    EditorMaterialTooling22,
    EditorMaterialToolingError,
    MaterialAssetSpec22,
    UniformValue22,
)
from .editor_preview import EditorViewportImage, RendererViewportBridge
from .graphics.camera3d import Camera3D
from .graphics.lights import DirectionalLight3D
from .graphics.mesh import Mesh3D, cube_mesh
from .graphics.shader_mesh import ShaderMesh3D
from .math.types import Vec3

_TEXTURE_SLOTS = {
    "albedo": "texture",
    "base_color": "texture",
    "metallic_roughness": "metallic_roughness_texture",
    "normal": "normal_texture",
    "occlusion": "occlusion_texture",
    "emissive": "emissive_texture",
}
_SURFACE_FIELDS = {
    "tint",
    "ambient",
    "diffuse",
    "specular",
    "shininess",
    "metallic",
    "roughness",
    "normal_scale",
    "occlusion_strength",
    "emissive_factor",
    "alpha_mode",
    "alpha_cutoff",
    "double_sided",
    "strict_uniforms",
}
_SHADER_HOOKS = {
    "vertex_globals",
    "vertex_surface",
    "fragment_globals",
    "fragment_surface",
    "fragment_lighting",
}


@dataclass(frozen=True, slots=True)
class MaterialPreset22:
    name: str
    label: str
    settings: tuple[tuple[str, object], ...]


MATERIAL_PRESETS_22 = (
    MaterialPreset22(
        "matte",
        "Matte",
        (
            ("metallic", 0.0),
            ("roughness", 0.85),
            ("alpha_mode", "OPAQUE"),
            ("double_sided", False),
            ("emissive_factor", (0.0, 0.0, 0.0, 1.0)),
        ),
    ),
    MaterialPreset22(
        "metal",
        "Polished Metal",
        (
            ("metallic", 1.0),
            ("roughness", 0.18),
            ("alpha_mode", "OPAQUE"),
            ("double_sided", False),
            ("emissive_factor", (0.0, 0.0, 0.0, 1.0)),
        ),
    ),
    MaterialPreset22(
        "glass",
        "Glass",
        (
            ("tint", (0.86, 0.94, 1.0, 0.35)),
            ("metallic", 0.0),
            ("roughness", 0.08),
            ("alpha_mode", "BLEND"),
            ("double_sided", True),
        ),
    ),
    MaterialPreset22(
        "emissive",
        "Emissive",
        (
            ("metallic", 0.0),
            ("roughness", 0.45),
            ("emissive_factor", (0.35, 0.7, 1.0, 1.0)),
            ("alpha_mode", "OPAQUE"),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class MaterialEditorFrame22:
    selected: str | None
    material_names: tuple[str, ...]
    dirty: bool
    missing_assets: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialLivePreview22:
    name: str
    image: EditorViewportImage | None
    scene_object_type: str
    shader_enabled: bool
    fingerprint: str
    diagnostics: tuple[str, ...]


class EditorMaterialPanelController22:
    """Toolkit-neutral Material/Shader Editor backed by shipping runtime objects."""

    def __init__(self, tooling: EditorMaterialTooling22) -> None:
        if not isinstance(tooling, EditorMaterialTooling22):
            raise TypeError("tooling must be an EditorMaterialTooling22")
        self.tooling = tooling
        names = tuple(item.name for item in tooling.snapshot().materials)
        self._selected = names[0] if names else None
        self._status = "Material/Shader Editor ready"

    @property
    def status(self) -> str:
        return self._status

    @property
    def selected(self) -> str | None:
        return self._selected

    @property
    def presets(self) -> tuple[MaterialPreset22, ...]:
        return MATERIAL_PRESETS_22

    def frame(self) -> MaterialEditorFrame22:
        snapshot = self.tooling.snapshot()
        names = tuple(item.name for item in snapshot.materials)
        if self._selected not in names:
            self._selected = names[0] if names else None
        if self._selected is None:
            return MaterialEditorFrame22(None, names, snapshot.dirty)

        missing = self.tooling.missing_assets(self._selected)
        diagnostics = tuple(f"Missing asset: {path}" for path in missing)
        return MaterialEditorFrame22(
            self._selected,
            names,
            snapshot.dirty,
            missing,
            diagnostics,
        )

    def selected_spec(self) -> MaterialAssetSpec22:
        if self._selected is None:
            raise EditorMaterialToolingError("no material is selected")
        return self._spec(self._selected)

    def select(self, name: str) -> MaterialEditorFrame22:
        self._spec(name)
        self._selected = name
        self._status = f"Selected material {name}"
        return self.frame()

    def create(self, name: str, *, preset: str | None = None) -> MaterialEditorFrame22:
        settings: dict[str, object] = {}
        if preset is not None:
            settings.update(dict(self._preset(preset).settings))
        self.tooling.create_material(name, **settings)
        self._selected = str(name).strip()
        self._status = f"Created material {self._selected}"
        return self.frame()

    def duplicate(self, new_name: str) -> MaterialEditorFrame22:
        selected = self.selected_spec().name
        self.tooling.duplicate_material(selected, new_name)
        self._selected = str(new_name).strip()
        self._status = f"Duplicated material as {self._selected}"
        return self.frame()

    def remove(self) -> MaterialEditorFrame22:
        selected = self.selected_spec().name
        self.tooling.remove_material(selected)
        self._selected = None
        self._status = f"Removed material {selected}"
        return self.frame()

    def apply_preset(self, preset: str) -> MaterialEditorFrame22:
        selected = self.selected_spec().name
        resolved = self._preset(preset)
        self.tooling.update_material(selected, **dict(resolved.settings))
        self._status = f"Applied {resolved.label} preset to {selected}"
        return self.frame()

    def update_surface(self, **changes: object) -> MaterialEditorFrame22:
        unknown = set(changes) - _SURFACE_FIELDS
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise EditorMaterialToolingError(f"unsupported surface field(s): {joined}")
        selected = self.selected_spec().name
        self.tooling.update_material(selected, **changes)
        self._status = f"Updated surface controls for {selected}"
        return self.frame()

    def set_texture(self, slot: str, path: str | None) -> MaterialEditorFrame22:
        key = str(slot).strip().lower()
        try:
            field = _TEXTURE_SLOTS[key]
        except KeyError as exc:
            raise EditorMaterialToolingError(
                "texture slot must be one of: " + ", ".join(sorted(_TEXTURE_SLOTS))
            ) from exc
        selected = self.selected_spec().name
        value = None if path is None or not str(path).strip() else str(path).strip()
        self.tooling.update_material(selected, **{field: value})
        self._status = f"Updated {key} texture for {selected}"
        return self.frame()

    def set_shader_define(self, name: str, value: DefineValue22) -> MaterialEditorFrame22:
        selected = self.selected_spec()
        pairs = _upsert_pair(selected.shader_defines, name, value)
        self.tooling.update_material(selected.name, shader_defines=pairs)
        self._status = f"Updated shader define {name}"
        return self.frame()

    def remove_shader_define(self, name: str) -> MaterialEditorFrame22:
        selected = self.selected_spec()
        self.tooling.update_material(
            selected.name,
            shader_defines=_remove_pair(selected.shader_defines, name),
        )
        self._status = f"Removed shader define {name}"
        return self.frame()

    def set_shader_hook(self, name: str, source: str) -> MaterialEditorFrame22:
        key = str(name).strip()
        if key not in _SHADER_HOOKS:
            raise EditorMaterialToolingError(
                "shader hook must be one of: " + ", ".join(sorted(_SHADER_HOOKS))
            )
        selected = self.selected_spec()
        pairs = _upsert_pair(selected.shader_hooks, key, str(source))
        self.tooling.update_material(selected.name, shader_hooks=pairs)
        self._status = f"Updated shader hook {key}"
        return self.frame()

    def remove_shader_hook(self, name: str) -> MaterialEditorFrame22:
        selected = self.selected_spec()
        self.tooling.update_material(
            selected.name,
            shader_hooks=_remove_pair(selected.shader_hooks, name),
        )
        self._status = f"Removed shader hook {name}"
        return self.frame()

    def set_shader_uniform(
        self,
        name: str,
        value: UniformValue22 | list[float],
    ) -> MaterialEditorFrame22:
        selected = self.selected_spec()
        pairs = _upsert_pair(selected.shader_uniforms, name, value)
        self.tooling.update_material(selected.name, shader_uniforms=pairs)
        self._status = f"Updated shader uniform {name}"
        return self.frame()

    def remove_shader_uniform(self, name: str) -> MaterialEditorFrame22:
        selected = self.selected_spec()
        self.tooling.update_material(
            selected.name,
            shader_uniforms=_remove_pair(selected.shader_uniforms, name),
        )
        self._status = f"Removed shader uniform {name}"
        return self.frame()

    def validate(self) -> tuple[str, ...]:
        selected = self.selected_spec()
        preview = self.tooling.preview(selected.name)
        diagnostics = [f"Missing asset: {path}" for path in preview.missing_assets]
        if preview.shader_material is not None:
            diagnostics.append(
                "Shader variant validated against the shipping swir_surface_3d template."
            )
        if not diagnostics:
            diagnostics.append("Material validated with no blocking diagnostics.")
        self._status = diagnostics[0]
        return tuple(diagnostics)

    def render_preview(
        self,
        viewport: RendererViewportBridge | Any,
        *,
        width: int = 420,
        height: int = 320,
    ) -> MaterialLivePreview22:
        selected = self.selected_spec()
        preview = self.tooling.preview(selected.name)
        if preview.missing_assets:
            diagnostics = tuple(
                f"Missing asset: {path}" for path in preview.missing_assets
            )
            self._status = "Live preview blocked by missing material assets"
            return MaterialLivePreview22(
                selected.name,
                None,
                "none",
                preview.shader_material is not None,
                preview.fingerprint,
                diagnostics,
            )
        if viewport is None or not callable(getattr(viewport, "capture", None)):
            raise EditorMaterialToolingError(
                "live material preview requires the editor shipping renderer"
            )

        scene = Scene()
        mesh = cube_mesh()
        if preview.shader_material is None:
            preview_object: object = Mesh3D(
                mesh,
                material=preview.material,
                name="__swir_material_preview__",
            )
        else:
            preview_object = ShaderMesh3D(
                mesh,
                preview.shader_material,
                color=preview.material.tint,
                name="__swir_shader_preview__",
            )
        scene.add(preview_object)
        scene.add(
            DirectionalLight3D(
                direction=Vec3(-0.45, -0.75, -0.5),
                intensity=1.15,
                name="__swir_preview_light__",
            )
        )
        camera = Camera3D(
            position=Vec3(2.35, 1.55, 3.1),
            target=Vec3(0.0, 0.0, 0.0),
            fov=48.0,
        )
        width = min(2048, max(64, int(width)))
        height = min(2048, max(64, int(height)))
        image = viewport.capture(
            scene,
            width,
            height,
            camera=camera,
            mode="3d",
        )
        if not isinstance(image, EditorViewportImage):
            raise TypeError("material preview renderer returned an invalid viewport image")

        diagnostics: list[str] = []
        if preview.shader_material is not None:
            diagnostics.append(
                "Custom shader preview uses the shipping ShaderMesh3D renderer path."
            )
        else:
            diagnostics.append(
                "Material preview uses the shipping Mesh3D/PBR renderer path."
            )
        self._status = f"Rendered live preview for {selected.name}"
        return MaterialLivePreview22(
            selected.name,
            image,
            type(preview_object).__name__,
            preview.shader_material is not None,
            preview.fingerprint,
            tuple(diagnostics),
        )

    def save(self) -> MaterialEditorFrame22:
        self.tooling.save()
        self._status = f"Saved material library {self.tooling.relative_path}"
        return self.frame()

    def _spec(self, name: str) -> MaterialAssetSpec22:
        clean = str(name)
        for item in self.tooling.snapshot().materials:
            if item.name == clean:
                return item
        raise EditorMaterialToolingError(f"unknown material {name!r}")

    @staticmethod
    def _preset(name: str) -> MaterialPreset22:
        clean = str(name).strip().lower()
        for preset in MATERIAL_PRESETS_22:
            if preset.name == clean:
                return preset
        raise EditorMaterialToolingError(
            "material preset must be one of: "
            + ", ".join(preset.name for preset in MATERIAL_PRESETS_22)
        )


class TkMaterialEditorApp22(TkBuildExportEditorApp21):
    """SwirEditor shell with integrated material/shader authoring and live preview."""

    def __init__(
        self,
        controller: Any,
        *,
        materials: EditorMaterialTooling22,
        material_preview_viewport: RendererViewportBridge | None = None,
        **kwargs: Any,
    ) -> None:
        self.material_editor_controller = EditorMaterialPanelController22(materials)
        self.material_preview_viewport = material_preview_viewport
        self._material_window: Any | None = None
        self._material_list: Any | None = None
        self._material_details_var: Any | None = None
        self._material_status_var: Any | None = None
        self._material_preview_label: Any | None = None
        self._material_preview_photo: Any | None = None
        super().__init__(controller, **kwargs)

    def install_creator_menu(self, menu: Any) -> None:
        super().install_creator_menu(menu)
        material_menu = self.tk.Menu(menu, tearoff=False)
        material_menu.add_command(
            label="Material / Shader Editor…",
            command=self._open_material_editor,
        )
        menu.add_cascade(label="Materials", menu=material_menu)

    def _open_material_editor(self) -> None:
        if self._material_window is not None and self._material_window.winfo_exists():
            self._material_window.deiconify()
            self._material_window.lift()
            self._material_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.title("SwirEditor 2.2 — Material / Shader Editor")
        window.geometry("1040x720")
        window.minsize(860, 600)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_material_editor)
        self._material_window = window

        body = self.ttk.Frame(window, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = self.ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        self.ttk.Label(left, text="Materials").pack(anchor="w")
        self._material_list = self.tk.Listbox(
            left,
            width=26,
            height=24,
            exportselection=False,
        )
        self._material_list.pack(fill="y", expand=True, pady=(6, 0))
        self._material_list.bind("<<ListboxSelect>>", self._material_select_from_list)

        right = self.ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        self._material_details_var = self.tk.StringVar()
        self._material_status_var = self.tk.StringVar()
        self.ttk.Label(
            right,
            textvariable=self._material_details_var,
            justify="left",
            wraplength=700,
        ).grid(row=0, column=0, sticky="ew")
        self.ttk.Label(
            right,
            textvariable=self._material_status_var,
            wraplength=700,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self._material_preview_label = self.ttk.Label(
            right,
            text="Live preview uses the shipping 3D renderer.",
            anchor="center",
        )
        self._material_preview_label.grid(row=2, column=0, sticky="nsew")

        actions = self.ttk.Frame(body)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        action_specs = (
            ("New", self._material_new),
            ("Duplicate", self._material_duplicate),
            ("Remove", self._material_remove),
            ("Preset", self._material_preset),
            ("Surface JSON", self._material_surface),
            ("Texture", self._material_texture),
            ("Shader Define", self._material_define),
            ("Shader Hook", self._material_hook),
            ("Shader Uniform", self._material_uniform),
            ("Validate", self._material_validate),
            ("Live Preview", self._material_preview),
            ("Save Library", self._material_save),
        )
        for index, (label, command) in enumerate(action_specs):
            self.ttk.Button(actions, text=label, command=command).grid(
                row=index // 6,
                column=index % 6,
                sticky="ew",
                padx=(0, 6),
                pady=(0, 6),
            )
        for column in range(6):
            actions.columnconfigure(column, weight=1)
        self._refresh_material_editor()

    def _close_material_editor(self) -> None:
        if self._material_window is not None:
            try:
                self._material_window.destroy()
            except Exception:
                pass
        self._material_window = None
        self._material_preview_photo = None

    def _refresh_material_editor(self) -> None:
        frame = self.material_editor_controller.frame()
        if self._material_list is not None:
            self._material_list.delete(0, self.tk.END)
            selected_index = None
            for index, name in enumerate(frame.material_names):
                self._material_list.insert(self.tk.END, name)
                if name == frame.selected:
                    selected_index = index
            if selected_index is not None:
                self._material_list.selection_set(selected_index)
                self._material_list.see(selected_index)

        if self._material_details_var is not None:
            if frame.selected is None:
                details = "No material selected."
            else:
                spec = self.material_editor_controller.selected_spec()
                shader = (
                    f"{len(spec.shader_defines)} defines · "
                    f"{len(spec.shader_hooks)} hooks · "
                    f"{len(spec.shader_uniforms)} uniforms"
                )
                details = (
                    f"{spec.name} · metallic={spec.metallic} · "
                    f"roughness={spec.roughness} · alpha={spec.alpha_mode} · {shader}"
                )
            self._material_details_var.set(details)
        if self._material_status_var is not None:
            suffix = " · unsaved" if frame.dirty else ""
            diagnostic = f" · {frame.diagnostics[0]}" if frame.diagnostics else ""
            self._material_status_var.set(
                self.material_editor_controller.status + suffix + diagnostic
            )

    def _material_select_from_list(self, _event: object) -> None:
        if self._material_list is None:
            return
        selection = self._material_list.curselection()
        if not selection:
            return
        name = str(self._material_list.get(selection[0]))
        self._material_action(lambda: self.material_editor_controller.select(name))

    def _material_new(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "New material",
            "Material name:",
            parent=self._material_window,
        )
        if name is None:
            return
        preset = simpledialog.askstring(
            "New material",
            "Preset (matte/metal/glass/emissive, blank = default):",
            initialvalue="matte",
            parent=self._material_window,
        )
        if preset is None:
            return
        self._material_action(
            lambda: self.material_editor_controller.create(
                name,
                preset=preset.strip() or None,
            )
        )

    def _material_duplicate(self) -> None:
        from tkinter import simpledialog

        current = self.material_editor_controller.selected_spec()
        name = simpledialog.askstring(
            "Duplicate material",
            "New material name:",
            initialvalue=f"{current.name}_copy",
            parent=self._material_window,
        )
        if name is not None:
            self._material_action(lambda: self.material_editor_controller.duplicate(name))

    def _material_remove(self) -> None:
        current = self.material_editor_controller.selected_spec()
        if self.messagebox.askyesno(
            "Remove material",
            f"Remove {current.name!r} from the project material library?",
            parent=self._material_window,
        ):
            self._material_action(self.material_editor_controller.remove)

    def _material_preset(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Material preset",
            "Preset: matte / metal / glass / emissive",
            initialvalue="matte",
            parent=self._material_window,
        )
        if name is not None:
            self._material_action(
                lambda: self.material_editor_controller.apply_preset(name)
            )

    def _material_surface(self) -> None:
        from tkinter import simpledialog

        spec = self.material_editor_controller.selected_spec()
        initial = json.dumps(
            {
                "tint": spec.tint,
                "metallic": spec.metallic,
                "roughness": spec.roughness,
                "normal_scale": spec.normal_scale,
                "occlusion_strength": spec.occlusion_strength,
                "emissive_factor": spec.emissive_factor,
                "alpha_mode": spec.alpha_mode,
                "alpha_cutoff": spec.alpha_cutoff,
                "double_sided": spec.double_sided,
            },
            sort_keys=True,
        )
        text = simpledialog.askstring(
            "Material surface",
            "Surface properties as JSON object:",
            initialvalue=initial,
            parent=self._material_window,
        )
        if text is None:
            return
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("surface JSON must be an object")
        except (json.JSONDecodeError, ValueError) as exc:
            self.messagebox.showerror(
                "SwirEditor — Material",
                str(exc),
                parent=self._material_window,
            )
            return
        self._material_action(
            lambda: self.material_editor_controller.update_surface(**payload)
        )

    def _material_texture(self) -> None:
        from tkinter import simpledialog

        slot = simpledialog.askstring(
            "Material texture",
            "Slot: albedo / metallic_roughness / normal / occlusion / emissive",
            initialvalue="albedo",
            parent=self._material_window,
        )
        if slot is None:
            return
        path = simpledialog.askstring(
            "Material texture",
            "Project assets-relative path (blank = clear):",
            parent=self._material_window,
        )
        if path is None:
            return
        self._material_action(
            lambda: self.material_editor_controller.set_texture(slot, path)
        )

    def _material_define(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Shader define",
            "Define name:",
            parent=self._material_window,
        )
        if name is None:
            return
        text = simpledialog.askstring(
            "Shader define",
            "JSON value (bool/int/float/string):",
            initialvalue="true",
            parent=self._material_window,
        )
        if text is None:
            return
        self._material_json_action(
            text,
            lambda value: self.material_editor_controller.set_shader_define(name, value),
        )

    def _material_hook(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Shader hook",
            "Hook: vertex_globals / vertex_surface / fragment_globals / "
            "fragment_surface / fragment_lighting",
            initialvalue="fragment_surface",
            parent=self._material_window,
        )
        if name is None:
            return
        source = simpledialog.askstring(
            "Shader hook",
            "Validated GLSL hook source:",
            initialvalue="surface_rgba.rgb *= 0.9;",
            parent=self._material_window,
        )
        if source is not None:
            self._material_action(
                lambda: self.material_editor_controller.set_shader_hook(name, source)
            )

    def _material_uniform(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Shader uniform",
            "Uniform name:",
            parent=self._material_window,
        )
        if name is None:
            return
        text = simpledialog.askstring(
            "Shader uniform",
            "JSON numeric scalar/vector value:",
            initialvalue="1.0",
            parent=self._material_window,
        )
        if text is None:
            return
        self._material_json_action(
            text,
            lambda value: self.material_editor_controller.set_shader_uniform(name, value),
        )

    def _material_validate(self) -> None:
        self._material_action(self.material_editor_controller.validate)

    def _material_preview(self) -> None:
        def render() -> MaterialLivePreview22:
            result = self.material_editor_controller.render_preview(
                self.material_preview_viewport
            )
            if result.image is not None and self._material_preview_label is not None:
                encoded = base64.b64encode(result.image.to_ppm()).decode("ascii")
                self._material_preview_photo = self.tk.PhotoImage(
                    data=encoded,
                    format="PPM",
                )
                self._material_preview_label.configure(
                    image=self._material_preview_photo,
                    text="",
                )
            return result

        self._material_action(render)

    def _material_save(self) -> None:
        self._material_action(self.material_editor_controller.save)

    def _material_json_action(self, text: str, operation: Any) -> None:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            self.messagebox.showerror(
                "SwirEditor — Material",
                str(exc),
                parent=self._material_window,
            )
            return
        self._material_action(lambda: operation(value))

    def _material_action(self, operation: Any) -> None:
        try:
            operation()
        except (
            EditorMaterialToolingError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.messagebox.showerror(
                "SwirEditor — Material",
                str(exc),
                parent=self._material_window,
            )
        self._refresh_material_editor()


def _upsert_pair(
    pairs: tuple[tuple[str, Any], ...],
    name: str,
    value: Any,
) -> tuple[tuple[str, Any], ...]:
    key = str(name).strip()
    if not key:
        raise EditorMaterialToolingError("shader parameter name cannot be empty")
    values = {pair_name: pair_value for pair_name, pair_value in pairs}
    values[key] = value
    return tuple(sorted(values.items()))


def _remove_pair(
    pairs: tuple[tuple[str, Any], ...],
    name: str,
) -> tuple[tuple[str, Any], ...]:
    key = str(name).strip()
    return tuple((pair_name, value) for pair_name, value in pairs if pair_name != key)
