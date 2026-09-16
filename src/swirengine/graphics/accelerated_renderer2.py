from __future__ import annotations

from typing import Any

from ..scene_acceleration import SceneAccelerationDiagnostics3D, SceneAccelerationRuntime3D
from .camera3d import Camera3D
from .csm_renderer import Renderer2


class SceneAcceleratedRenderer2(Renderer2):
    """Opt-in Renderer2 executor that consumes a scene-attached visibility runtime.

    Attach a runtime with ``enable_scene_acceleration(scene)``. When no runtime is attached this
    class behaves exactly like the normal Renderer2 path. GPU particle submission remains on the
    original scene after the base render, while the depth/prepass/CSM/base/decal planning path sees
    the accelerated candidate view.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._scene_acceleration_diagnostics: SceneAccelerationDiagnostics3D | None = None

    @property
    def scene_acceleration_diagnostics(self) -> SceneAccelerationDiagnostics3D | None:
        return self._scene_acceleration_diagnostics

    def _render_3d(self, scene: object, camera: Camera3D) -> None:
        runtime = getattr(scene, "scene_acceleration", None)
        if runtime is None:
            self._scene_acceleration_diagnostics = None
            super()._render_3d(scene, camera)
            return
        if not isinstance(runtime, SceneAccelerationRuntime3D):
            raise TypeError("scene.scene_acceleration must be SceneAccelerationRuntime3D")
        frame = runtime.frame(
            scene,
            camera,
            width=self.width,
            height=self.height,
        )
        self._scene_acceleration_diagnostics = frame.diagnostics
        super()._render_3d(frame.view, camera)
