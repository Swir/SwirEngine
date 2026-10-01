from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from swirengine.core.scene import Scene
from swirengine.editor_lighting22 import (
    EditorLightingPanelController22,
    LightingScenePreview22,
    LightingSceneSource22,
)
from swirengine.editor_render_backend21 import EditorRenderBackend21, ResizableFramebufferTarget
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.graphics.renderer import Renderer
from swirengine.lighting_authoring22 import EditorLightingTooling22, LightSpec22
from swirengine.math.types import Color, Vec3
from swirengine.serialization import SceneSerializer


@pytest.mark.parametrize("mode", ("2d", "3d"))
def test_creator_panel_renders_live_changes_with_owned_gpu_context(tmp_path: Path, mode: str) -> None:
    if os.environ.get("SWIR_LIGHTING_REQUIRE_GL") != "1":
        pytest.skip("required by the dedicated real EGL workflow")
    import moderngl

    def backend(width, height):
        ctx = moderngl.create_standalone_context(require=330, backend="egl")
        target = ResizableFramebufferTarget(ctx, width, height)
        return EditorRenderBackend21(ctx=ctx, renderer=Renderer(ctx, width, height), target=target)

    def factory(tool, source):
        return LightingScenePreview22(tool, source, backend_factory=backend)

    scene = Scene()
    scene.add(Cube3D(position=Vec3(0, 0, -4), color=Color(.6, .4, .2, 1)) if mode == "3d"
              else Rectangle2D(24, 24, 48, 48, Color(.6, .4, .2, 1)))
    serializer = SceneSerializer()
    source = LightingSceneSource22("scenes/main.swirscene", mode, scene,
                                  Camera3D() if mode == "3d" else Camera2D(), serializer)
    original = serializer.dumps_scene(scene)
    tool = EditorLightingTooling22(tmp_path)
    panel = EditorLightingPanelController22(tool, lambda: source, preview_factory=factory)
    if mode == "3d":
        panel.set_light(LightSpec22("sun"))
        panel.update_section("renderer", shadow_resolution=128, shadow_cascades=2,
                             ssao_samples=8, bloom_levels=2)
    panel.update_section("postfx", exposure=0.3, fxaa=False)
    panel.save()
    panel.start()
    try:
        first = panel.capture(96, 96)
        assert first is not None
        assert len(first.rgb) == 96 * 96 * 3
        first_renderer = panel._preview._backend.renderer
        panel.capture(96, 96)
        assert panel._preview._backend.renderer is first_renderer
        panel.update_section("postfx", exposure=3.0)
        second = panel.capture(96, 96)
        assert second is not None
        low = np.frombuffer(first.rgb, dtype=np.uint8)
        high = np.frombuffer(second.rgb, dtype=np.uint8)
        assert low.max() > low.min()
        assert float(high.mean()) > float(low.mean()) + 1.0
        panel.pause()
        backend_instance = panel._preview._backend
        assert panel.capture(96, 96) is second
        assert panel.capture(64, 48, step=True).width == 64
        assert panel._preview._backend is backend_instance
        assert backend_instance.ctx.error == "GL_NO_ERROR"
        assert serializer.dumps_scene(scene) == original
    finally:
        panel.stop()
    assert not panel.active and panel.image is None
    assert backend_instance._released
    assert serializer.dumps_scene(scene) == original
