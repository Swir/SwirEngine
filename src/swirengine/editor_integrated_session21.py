from __future__ import annotations

from dataclasses import replace
from typing import Any

from .editor_animation_tooling21 import EditorAnimationToolingError
from .editor_app21 import EditorProjectSession, EditorProjectSummary
from .editor_audio_tooling21 import EditorAudioTooling21, EditorAudioToolingError
from .editor_build_export_tooling21 import (
    EditorBuildExportTooling21,
    EditorBuildExportToolingError,
)
from .editor_material_tooling22 import EditorMaterialTooling22, EditorMaterialToolingError
from .editor_navigation_tooling21 import EditorNavigationToolingError
from .editor_physics_tooling21 import EditorPhysicsToolingError
from .editor_save_profile_tooling21 import (
    EditorSaveProfileTooling21,
    EditorSaveProfileToolingError,
)
from .editor_ui_tooling21 import EditorUIHudTooling21, EditorUIHudToolingError
from .editor_visual_scripting22 import (
    EditorVisualScriptingError22,
    EditorVisualScriptingTooling22,
)
from .serialization import SceneSerializationError

_SAVE_ERRORS = (
    OSError,
    SceneSerializationError,
    EditorAnimationToolingError,
    EditorPhysicsToolingError,
    EditorNavigationToolingError,
    EditorAudioToolingError,
    EditorUIHudToolingError,
    EditorSaveProfileToolingError,
    EditorBuildExportToolingError,
    EditorMaterialToolingError,
    EditorVisualScriptingError22,
    TypeError,
    ValueError,
)


class EditorIntegratedProjectSession21(EditorProjectSession):
    """SwirEditor project session that persists integrated creator tooling."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.audio = EditorAudioTooling21(self.manifest.root)
        self.ui_hud = EditorUIHudTooling21(self.manifest.root)
        self.save_profile = EditorSaveProfileTooling21(
            self.manifest.root,
            project_name=self.manifest.name,
        )
        self.build_export = EditorBuildExportTooling21(
            self.manifest.root,
            project_name=self.manifest.name,
        )
        self.materials = EditorMaterialTooling22(self.manifest.root)
        self.visual_scripts = EditorVisualScriptingTooling22(self.manifest.root)

    @classmethod
    def adopt(cls, session: EditorProjectSession) -> EditorIntegratedProjectSession21:
        """Promote an already-open Project Hub session without reopening project resources."""

        if isinstance(session, cls):
            return session
        if not isinstance(session, EditorProjectSession):
            raise TypeError("session must be an EditorProjectSession")
        integrated = cls.__new__(cls)
        integrated.__dict__.update(session.__dict__)
        integrated.audio = EditorAudioTooling21(integrated.manifest.root)
        integrated.ui_hud = EditorUIHudTooling21(integrated.manifest.root)
        integrated.save_profile = EditorSaveProfileTooling21(
            integrated.manifest.root,
            project_name=integrated.manifest.name,
        )
        integrated.build_export = EditorBuildExportTooling21(
            integrated.manifest.root,
            project_name=integrated.manifest.name,
        )
        integrated.materials = EditorMaterialTooling22(integrated.manifest.root)
        integrated.visual_scripts = EditorVisualScriptingTooling22(integrated.manifest.root)
        return integrated

    def summary(self) -> EditorProjectSummary:
        summary = super().summary()
        return replace(
            summary,
            dirty=(
                summary.dirty
                or self.audio.dirty
                or self.ui_hud.dirty
                or self.save_profile.dirty
                or self.build_export.dirty
                or self.materials.dirty
                or self.visual_scripts.dirty
            ),
        )

    def save(self):
        audio_was_dirty = self.audio.dirty
        ui_hud_was_dirty = self.ui_hud.dirty
        save_profile_was_dirty = self.save_profile.dirty
        build_export_was_dirty = self.build_export.dirty
        materials_were_dirty = self.materials.dirty
        visual_scripts_were_dirty = self.visual_scripts.dirty
        if audio_was_dirty:
            self.audio.save()
        if ui_hud_was_dirty:
            self.ui_hud.save()
        if save_profile_was_dirty:
            self.save_profile.save()
        if build_export_was_dirty:
            self.build_export.save()
        if materials_were_dirty:
            self.materials.save()
        if visual_scripts_were_dirty:
            self.visual_scripts.save()
        state = super().save()
        if audio_was_dirty:
            self.console.write(
                f"Saved audio configuration {self.audio.relative_path}",
                source="swireditor",
            )
        if ui_hud_was_dirty:
            self.console.write(
                f"Saved UI/HUD configuration {self.ui_hud.relative_path}",
                source="swireditor",
            )
        if save_profile_was_dirty:
            self.console.write(
                f"Saved save/profile configuration {self.save_profile.relative_path}",
                source="swireditor",
            )
        if build_export_was_dirty:
            self.console.write(
                f"Saved build/export configuration {self.build_export.relative_path}",
                source="swireditor",
            )
        if materials_were_dirty:
            self.console.write(
                f"Saved material library {self.materials.relative_path}",
                source="swireditor",
            )
        if visual_scripts_were_dirty:
            self.console.write(
                f"Saved visual scripts {self.visual_scripts.relative_dir}",
                source="swireditor",
            )
        return state

    def run(self) -> None:
        from .editor_asset_app21 import run_editor_session21

        run_editor_session21(self)

    def _all_dirty(self) -> bool:
        return bool(
            self.scenes.dirty
            or self.gameplay.dirty
            or self.animation.dirty
            or self.physics.dirty
            or self.navigation.dirty
            or self.audio.dirty
            or self.ui_hud.dirty
            or self.save_profile.dirty
            or self.build_export.dirty
            or self.materials.dirty
            or self.visual_scripts.dirty
        )

    def _save_from_ui(self, app: Any) -> None:
        try:
            self.save()
        except _SAVE_ERRORS as exc:
            self.console.write(str(exc), level="error", source="swireditor")
            app.messagebox.showerror(
                "SwirEditor — Save failed",
                str(exc),
                parent=app.root,
            )

    def _close_from_ui(self, app: Any) -> None:
        if self._all_dirty():
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
                except _SAVE_ERRORS as exc:
                    self.console.write(str(exc), level="error", source="swireditor")
                    app.messagebox.showerror(
                        "SwirEditor — Save failed",
                        str(exc),
                        parent=app.root,
                    )
                    return
            else:
                self.scenes.discard_recovery()
        app.close()
