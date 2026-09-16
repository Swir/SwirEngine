from __future__ import annotations

from typing import Any

from ..scene_acceleration import SceneAccelerationDiagnostics3D, SceneAccelerationRuntime3D
from .camera3d import Camera3D
from .csm_renderer import Renderer2
from .hiz_gpu import HiZPyramidPass3D


class SceneAcceleratedRenderer2(Renderer2):
    """Opt-in Renderer2 executor that consumes a scene-attached visibility runtime.

    Attach a runtime with ``enable_scene_acceleration(scene)``. When no runtime is attached this
    class behaves exactly like the normal Renderer2 path. GPU particle submission remains on the
    original scene after the base render, while the depth/prepass/CSM/base/decal planning path sees
    the accelerated candidate view. When acceleration is active, the sampleable Renderer2 depth
    target is reduced into a conservative maximum-depth Hi-Z chain after the frame without CPU
    readback, providing the occlusion-ready GPU resource for subsequent visibility stages.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._scene_acceleration_diagnostics: SceneAccelerationDiagnostics3D | None = None
        self._hiz_pass = HiZPyramidPass3D(self.ctx)

    @property
    def scene_acceleration_diagnostics(self) -> SceneAccelerationDiagnostics3D | None:
        return self._scene_acceleration_diagnostics

    @property
    def hiz_level_count(self) -> int:
        return self._hiz_pass.level_count

    @property
    def hiz_textures(self) -> tuple[object, ...]:
        return self._hiz_pass.textures

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

    def render(self, scene, *, camera=None, clear_color=(0.035, 0.045, 0.07, 1.0)) -> None:
        super().render(scene, camera=camera, clear_color=clear_color)
        if (
            self.mode == "3d"
            and getattr(scene, "scene_acceleration", None) is not None
            and self._post_depth is not None
        ):
            self._hiz_pass.build(self._post_depth, width=self.width, height=self.height)
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, self.width, self.height)

    def release(self) -> None:
        self._hiz_pass.release()
        super().release()
