from __future__ import annotations

from types import SimpleNamespace

import moderngl
import numpy as np

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.csm_renderer import CascadedDirectionalShadowMap
from swirengine.graphics.lights import DirectionalLight3D
from swirengine.graphics.mesh import Mesh3D, cube_mesh
from swirengine.graphics.primitives import Cube3D
from swirengine.graphics.renderer2 import Decal3D, Renderer2Settings
from swirengine.graphics.renderer2_effects import (
    BloomPass3D,
    DecalPass3D,
    DepthNormalPrepass3D,
    SSAOPass3D,
)
from swirengine.math.types import Color, Vec3


def main() -> None:
    width, height = 192, 108
    ctx = moderngl.create_standalone_context(require=330, backend="egl")
    settings = Renderer2Settings(
        shadow_cascades=2,
        shadow_resolution=128,
        shadow_distance=48.0,
        ssao_samples=8,
        bloom_levels=3,
        max_decals=8,
    )
    camera = Camera3D(
        position=Vec3(0.0, 1.5, 5.0),
        target=Vec3(0.0, 0.0, 0.0),
        near=0.1,
        far=100.0,
    )
    light = DirectionalLight3D(direction=Vec3(-0.6, -1.0, -0.35))
    scene = SimpleNamespace(
        objects=[
            light,
            Cube3D(position=Vec3(-1.0, 0.0, 0.0)),
            Mesh3D(cube_mesh(), position=Vec3(1.0, 0.0, -1.0)),
        ]
    )

    csm = CascadedDirectionalShadowMap(ctx, settings)
    prepass = DepthNormalPrepass3D(ctx)
    ssao = SSAOPass3D(ctx)
    bloom = BloomPass3D(ctx)
    decals = DecalPass3D(ctx)
    depth_texture = ctx.depth_texture((width, height))
    depth_texture.repeat_x = False
    depth_texture.repeat_y = False
    hdr_texture = ctx.texture((width, height), 4, dtype="f2")
    hdr_texture.filter = (ctx.LINEAR, ctx.LINEAR)
    hdr_framebuffer = ctx.framebuffer(color_attachments=[hdr_texture])
    invalid_depth = None
    invalid_normal = None

    try:
        shadow_frame = csm.render(scene, light, camera, width=width, height=height)
        assert len(shadow_frame.light_frames) == settings.shadow_cascades
        assert len(shadow_frame.plan.cascades) == settings.shadow_cascades

        prepass_draws = prepass.render(
            scene,
            camera,
            width=width,
            height=height,
            depth_texture=depth_texture,
        )
        assert prepass_draws == 2
        assert prepass.normal_texture is not None

        ao_texture = ssao.render(
            depth_texture=depth_texture,
            normal_texture=prepass.normal_texture,
            camera=camera,
            width=width,
            height=height,
            settings=settings,
        )
        assert ao_texture is not None
        assert len(ao_texture.read()) == width * height

        # Dynamic Renderer 1.3 paths can write depth after the static normal prepass. Alpha=0
        # marks those pixels as lacking a valid normal; Renderer2 must leave their AO at 1.0.
        mask_size = (8, 8)
        invalid_depth = ctx.texture(
            mask_size,
            1,
            np.full(mask_size[0] * mask_size[1], 0.5, dtype="f4").tobytes(),
            dtype="f4",
        )
        invalid_normal = ctx.texture(
            mask_size,
            4,
            bytes((128, 128, 255, 0)) * (mask_size[0] * mask_size[1]),
            dtype="f1",
        )
        masked_ao = ssao.render(
            depth_texture=invalid_depth,
            normal_texture=invalid_normal,
            camera=camera,
            width=mask_size[0],
            height=mask_size[1],
            settings=settings,
        )
        assert set(masked_ao.read()) == {255}

        hdr_framebuffer.use()
        hdr_framebuffer.clear(2.4, 1.4, 0.35, 1.0)
        bloom_texture = bloom.render(
            hdr_texture,
            width=width,
            height=height,
            settings=settings,
        )
        assert bloom_texture is not None
        assert len(bloom_texture.read()) > 0

        decal_draws = decals.render(
            (
                Decal3D(
                    position=Vec3(0.0, 0.0, 0.0),
                    size=Vec3(8.0, 8.0, 8.0),
                    color=Color(0.2, 0.8, 1.0, 0.65),
                ),
            ),
            color_texture=hdr_texture,
            depth_texture=depth_texture,
            camera=camera,
            width=width,
            height=height,
            texture_loader=lambda _path: hdr_texture,
        )
        assert decal_draws == 1
        ctx.finish()
    finally:
        if invalid_normal is not None:
            invalid_normal.release()
        if invalid_depth is not None:
            invalid_depth.release()
        decals.release()
        bloom.release()
        ssao.release()
        prepass.release()
        csm.release()
        hdr_framebuffer.release()
        hdr_texture.release()
        depth_texture.release()
        ctx.release()

    print("Renderer 2.0 headless OpenGL smoke: PASS")


if __name__ == "__main__":
    main()
