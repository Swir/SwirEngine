from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from swirengine.core.game import Game
from swirengine.graphics.csm_renderer import Renderer2
from swirengine.graphics.postprocess import PostProcessRenderer
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.graphics.renderer2 import Renderer2Settings
from swirengine.lighting_authoring22 import (
    EditorLightingTooling22,
    LightSpec22,
    PostFXSpec22,
    SceneLightingSpec22,
)
from swirengine.math.types import Color, Vec3


class ScreenContext:
    """Bind the real standalone context's output to a real offscreen framebuffer."""

    def __init__(self, context, screen) -> None:
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "screen", screen)

    def __getattr__(self, name):
        return getattr(self._context, name)

    def __setattr__(self, name, value):
        setattr(self._context, name, value)


@pytest.mark.parametrize("mode", ("2d", "3d"))
def test_saved_profile_changes_real_opengl_output(tmp_path: Path, mode: str) -> None:
    if os.environ.get("SWIR_LIGHTING_REQUIRE_GL") != "1":
        pytest.skip("real EGL gate is explicitly enabled by the Lighting 2.2 workflow")
    # No importorskip/context fallback here: missing GL must fail the required gate.
    import moderngl

    ctx = moderngl.create_standalone_context(require=330, backend="egl")
    framebuffer = ctx.simple_framebuffer((96, 96), components=4)
    screen = ScreenContext(ctx, framebuffer)
    try:
        tool = EditorLightingTooling22(tmp_path)
        profile = SceneLightingSpec22(
            "scenes/main.swirscene", mode=mode,
            lights=(LightSpec22("sun"),) if mode == "3d" else (),
            postfx=PostFXSpec22(exposure=0.3, fxaa=False),
            renderer=Renderer2Settings(shadow_resolution=128, shadow_cascades=2,
                                       ssao_samples=8, bloom_levels=2),
        )
        tool.set_profile(profile)
        tool.save()
        reopened = EditorLightingTooling22(tmp_path)
        frames = []
        for exposure in (0.3, 3.0):
            reopened.update(profile.scene, postfx=PostFXSpec22(exposure=exposure, fxaa=False))
            runtime = reopened.build_runtime(profile.scene)
            game = Game(mode=mode, width=96, height=96)
            if mode == "3d":
                game.add(Cube3D(position=Vec3(0, 0, -4), color=Color(0.6, 0.4, 0.2, 1)))
            else:
                game.add(Rectangle2D(24, 24, 48, 48, Color(0.6, 0.4, 0.2, 1)))
            mount = runtime.apply_to_game(game)
            framebuffer.use()
            renderer = (
                Renderer2(screen, 96, 96, mode, postprocess=game.postprocess,
                          renderer2=game.renderer2_settings)
                if mode == "3d" else
                PostProcessRenderer(screen, 96, 96, mode, postprocess=game.postprocess)
            )
            try:
                renderer.render(game.scene, camera=game.camera)
                ctx.finish()
                frame = np.frombuffer(framebuffer.read(components=3, alignment=1), dtype=np.uint8)
                assert frame.size == 96 * 96 * 3
                assert frame.max() > frame.min()
                frames.append(frame.copy())
                if mode == "3d":
                    assert renderer.renderer2_diagnostics.hdr_resolves == 1
                    assert renderer.renderer2_diagnostics.shadow_cascades == 2
                assert ctx.error == "GL_NO_ERROR"
            finally:
                renderer.release()
                mount.unmount()
        assert float(frames[1].mean()) > float(frames[0].mean()) + 1.0
    finally:
        framebuffer.release()
        ctx.release()
