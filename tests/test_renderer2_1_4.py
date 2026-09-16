from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import pytest

from swirengine import (
    Decal3D as PublicDecal3D,
    Game,
    Renderer2 as PublicRenderer2,
    Renderer2Settings as PublicRenderer2Settings,
)
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.csm_renderer import (
    CascadedDirectionalShadowMap,
    Renderer2 as Renderer2Implementation,
)
from swirengine.graphics.lights import DirectionalLight3D, PointLight3D
from swirengine.graphics.mesh import Mesh3D, cube_mesh
from swirengine.graphics.primitives import Cube3D
from swirengine.graphics.renderer2 import (
    Decal3D,
    Renderer2Planner,
    Renderer2Settings,
    build_cascaded_shadow_plan,
    practical_cascade_splits,
)
from swirengine.math.types import Vec3


@dataclass
class SceneStub:
    objects: list[object]


class _Uniform:
    def __init__(self) -> None:
        self.data = b""

    def write(self, data: bytes) -> None:
        self.data = data


class _Program:
    def __init__(self) -> None:
        self.uniform = _Uniform()
        self.released = False

    def __getitem__(self, name: str):
        assert name == "light_mvp"
        return self.uniform

    def release(self) -> None:
        self.released = True


class _Resource:
    def __init__(self) -> None:
        self.released = False
        self.used_locations: list[int] = []

    def release(self) -> None:
        self.released = True

    def use(self, location: int = 0) -> None:
        self.used_locations.append(location)


class _DepthTexture(_Resource):
    def __init__(self, size: tuple[int, int]) -> None:
        super().__init__()
        self.size = size
        self.repeat_x = True
        self.repeat_y = True
        self.compare_func = "legacy"


class _Framebuffer(_Resource):
    def __init__(self, depth_attachment: _DepthTexture) -> None:
        super().__init__()
        self.depth_attachment = depth_attachment
        self.clear_depths: list[float] = []
        self.use_count = 0

    def use(self) -> None:
        self.use_count += 1

    def clear(self, *, depth: float) -> None:
        self.clear_depths.append(depth)


class _Vao(_Resource):
    def __init__(self) -> None:
        super().__init__()
        self.render_counts: list[int] = []

    def render(self, *, vertices: int) -> None:
        self.render_counts.append(vertices)


class _Ctx:
    DEPTH_TEST = 1

    def __init__(self) -> None:
        self.viewport = (0, 0, 1280, 720)
        self.program_obj = _Program()
        self.depth_textures: list[_DepthTexture] = []
        self.framebuffers: list[_Framebuffer] = []
        self.vaos: list[_Vao] = []
        self.buffers: list[_Resource] = []
        self.enabled: list[int] = []

    def program(self, **_kwargs):
        return self.program_obj

    def depth_texture(self, size: tuple[int, int]):
        texture = _DepthTexture(size)
        self.depth_textures.append(texture)
        return texture

    def framebuffer(self, *, depth_attachment):
        framebuffer = _Framebuffer(depth_attachment)
        self.framebuffers.append(framebuffer)
        return framebuffer

    def buffer(self, _data: bytes):
        buffer = _Resource()
        self.buffers.append(buffer)
        return buffer

    def vertex_array(self, _program, _bindings):
        vao = _Vao()
        self.vaos.append(vao)
        return vao

    def enable(self, flag: int) -> None:
        self.enabled.append(flag)


def test_renderer2_creator_api_is_exported_from_top_level_package() -> None:
    assert PublicRenderer2 is Renderer2Implementation
    assert PublicRenderer2Settings is Renderer2Settings
    assert PublicDecal3D is Decal3D


def test_game_configures_renderer2_atomically_and_creates_decals() -> None:
    game = Game(mode="3d")
    configured = game.configure_renderer2(
        shadow_cascades=3,
        ssao_samples=32,
        bloom_levels=4,
        max_decals=64,
    )

    assert game.renderer2_enabled is True
    assert game.renderer2_settings is configured
    assert configured.shadow_cascades == 3
    assert configured.ssao_samples == 32
    assert configured.bloom_levels == 4
    assert configured.max_decals == 64

    decal = game.decal(position=Vec3(1.0, 0.0, -3.0), size=Vec3(2.0, 1.0, 2.0))
    assert isinstance(decal, PublicDecal3D)
    assert decal in game.scene.objects

    previous = game.renderer2_settings
    with pytest.raises(ValueError, match="shadow_cascades"):
        game.configure_renderer2(shadow_cascades=0)
    assert game.renderer2_settings is previous

    with pytest.raises(TypeError, match="unknown Renderer2 setting"):
        game.configure_renderer2(not_a_renderer_option=True)

    with pytest.raises(RuntimeError, match="requires mode='3d'"):
        Game(mode="2d").configure_renderer2()


def test_practical_cascade_splits_are_monotonic_and_cover_far_plane() -> None:
    splits = practical_cascade_splits(0.1, 100.0, 4, 0.72)

    assert len(splits) == 4
    assert all(a < b for a, b in pairwise(splits))
    assert splits[-1] == pytest.approx(100.0)


def test_practical_cascade_split_extremes_match_uniform_and_logarithmic_modes() -> None:
    uniform = practical_cascade_splits(1.0, 81.0, 4, 0.0)
    logarithmic = practical_cascade_splits(1.0, 81.0, 4, 1.0)

    assert uniform == pytest.approx((21.0, 41.0, 61.0, 81.0))
    assert logarithmic == pytest.approx((3.0, 9.0, 27.0, 81.0))


def test_cascade_plan_clamps_to_shadow_distance_and_selects_depth() -> None:
    camera = Camera3D(
        position=Vec3(0.0, 2.0, 6.0),
        target=Vec3(0.0, 2.0, 5.0),
        near=0.1,
        far=500.0,
    )
    settings = Renderer2Settings(shadow_distance=96.0, shadow_cascades=4)

    plan = build_cascaded_shadow_plan(camera, aspect=16.0 / 9.0, settings=settings)

    assert plan.near == pytest.approx(0.1)
    assert plan.far == pytest.approx(96.0)
    assert len(plan.cascades) == 4
    assert plan.cascades[-1].far == pytest.approx(96.0)
    assert plan.cascade_for_depth(0.1).index == 0
    assert plan.cascade_for_depth(500.0).index == 3
    assert all(cascade.extent > 0.0 for cascade in plan.cascades)
    assert all(cascade.texel_world_size > 0.0 for cascade in plan.cascades)


def test_cascade_focus_is_stable_for_sub_texel_camera_motion() -> None:
    camera = Camera3D(position=Vec3(), target=Vec3(0.0, 0.0, -1.0), near=0.1, far=100.0)
    settings = Renderer2Settings(shadow_distance=80.0, shadow_resolution=2048)
    first = build_cascaded_shadow_plan(camera, aspect=1.0, settings=settings)
    texel = first.cascades[0].texel_world_size

    camera.position.x += texel * 0.2
    camera.target.x += texel * 0.2
    second = build_cascaded_shadow_plan(camera, aspect=1.0, settings=settings)

    assert second.cascades[0].focus.x == pytest.approx(first.cascades[0].focus.x)


def test_renderer2_planner_schedules_production_passes_and_diagnostics() -> None:
    scene = SceneStub(
        [
            DirectionalLight3D(),
            Cube3D(position=Vec3(0.0, 0.0, -4.0)),
            Cube3D(position=Vec3(2.0, 0.0, -6.0)),
            Decal3D(position=Vec3(0.0, 0.0, -3.0)),
        ]
    )
    planner = Renderer2Planner(Renderer2Settings(shadow_cascades=4, bloom_levels=4))

    plan = planner.plan(scene, Camera3D(), width=1920, height=1080)
    diagnostics = plan.diagnostics

    assert plan.has_pass("depth_prepass")
    assert plan.has_pass("shadow_cascades")
    assert plan.has_pass("opaque")
    assert plan.has_pass("decals")
    assert plan.has_pass("ssao")
    assert plan.has_pass("bloom_extract")
    assert plan.has_pass("bloom_downsample")
    assert plan.has_pass("bloom_upsample")
    assert plan.has_pass("hdr_resolve")
    assert diagnostics.visible_opaque == 2
    assert diagnostics.depth_prepass_draws == 2
    assert diagnostics.shadow_cascades == 4
    assert diagnostics.shadow_draws == 8
    assert diagnostics.decals_submitted == 1
    assert diagnostics.ssao_passes == 2
    assert diagnostics.bloom_passes == 8  # extract + 4 down + 3 up
    assert diagnostics.estimated_draw_calls == sum(item.draw_calls for item in plan.passes)


def test_renderer2_planner_omits_shadow_pass_when_only_non_directional_light_is_active() -> None:
    scene = SceneStub([PointLight3D(), Cube3D(position=Vec3(0.0, 0.0, -4.0))])

    plan = Renderer2Planner().plan(scene, Camera3D(), width=1280, height=720)

    assert plan.cascades is None
    assert not plan.has_pass("shadow_cascades")
    assert plan.has_pass("opaque")


def test_renderer2_decal_budget_is_bounded_and_deterministic() -> None:
    near = Decal3D(position=Vec3(0.0, 0.0, -1.0), layer=0)
    far = Decal3D(position=Vec3(0.0, 0.0, -10.0), layer=0)
    foreground = Decal3D(position=Vec3(0.0, 0.0, -20.0), layer=-1)
    scene = SceneStub([near, far, foreground])
    settings = Renderer2Settings(max_decals=2, ssao=False, bloom=False, hdr=False)

    plan = Renderer2Planner(settings).plan(scene, Camera3D(), width=800, height=600)

    assert plan.decals == (foreground, near)
    assert plan.diagnostics.decal_candidates == 3
    assert plan.diagnostics.decals_submitted == 2
    assert plan.diagnostics.decals_dropped == 1


def test_renderer2_can_disable_expensive_optional_passes() -> None:
    scene = SceneStub([DirectionalLight3D(), Cube3D()])
    settings = Renderer2Settings(
        cascaded_shadows=False,
        depth_prepass=False,
        ssao=False,
        bloom=False,
        decals=False,
        hdr=False,
    )

    plan = Renderer2Planner(settings).plan(scene, Camera3D(), width=640, height=480)

    assert tuple(item.name for item in plan.passes) == ("opaque",)
    assert plan.diagnostics.estimated_draw_calls == 1


def test_csm_allocates_one_depth_target_per_cascade_and_renders_meshes_and_cubes() -> None:
    ctx = _Ctx()
    settings = Renderer2Settings(shadow_cascades=4, shadow_resolution=512)
    csm = CascadedDirectionalShadowMap(ctx, settings)
    mesh = Mesh3D(cube_mesh(), position=Vec3(2.0, 0.0, -5.0))
    cube = Cube3D(position=Vec3(-2.0, 0.0, -5.0))
    hidden = Cube3D(position=Vec3(0.0, 0.0, -5.0), visible=False)
    scene = SceneStub([mesh, cube, hidden])

    frame = csm.render(
        scene,
        DirectionalLight3D(),
        Camera3D(),
        width=1280,
        height=720,
    )

    assert ctx.viewport == (0, 0, 1280, 720)
    assert len(frame.plan.cascades) == 4
    assert len(frame.light_frames) == 4
    assert [texture.size for texture in ctx.depth_textures] == [(512, 512)] * 4
    assert all(texture.repeat_x is False for texture in ctx.depth_textures)
    assert all(texture.repeat_y is False for texture in ctx.depth_textures)
    assert all(texture.compare_func == "" for texture in ctx.depth_textures)
    assert all(framebuffer.clear_depths == [1.0] for framebuffer in ctx.framebuffers)
    assert len(ctx.vaos) == 2
    assert all(vao.render_counts == [36, 36, 36, 36] for vao in ctx.vaos)
    assert len(ctx.program_obj.uniform.data) == 64

    csm.use(2, location=7)
    assert ctx.depth_textures[2].used_locations == [7]


def test_csm_reuses_gpu_meshes_across_frames_and_releases_every_resource() -> None:
    ctx = _Ctx()
    settings = Renderer2Settings(shadow_cascades=2, shadow_resolution=256)
    csm = CascadedDirectionalShadowMap(ctx, settings)
    mesh = Mesh3D(cube_mesh())
    cube = Cube3D(position=Vec3(2.0, 0.0, -4.0))
    scene = SceneStub([mesh, cube])
    camera = Camera3D()
    light = DirectionalLight3D()

    csm.render(scene, light, camera, width=800, height=600)
    csm.render(scene, light, camera, width=800, height=600)

    assert len(ctx.depth_textures) == 2
    assert len(ctx.framebuffers) == 2
    assert len(ctx.buffers) == 2
    assert len(ctx.vaos) == 2
    assert all(vao.render_counts == [36, 36, 36, 36] for vao in ctx.vaos)

    csm.release()
    csm.release()
    assert all(resource.released for resource in ctx.depth_textures)
    assert all(resource.released for resource in ctx.framebuffers)
    assert all(resource.released for resource in ctx.buffers)
    assert all(resource.released for resource in ctx.vaos)
    assert ctx.program_obj.released is True

    with pytest.raises(RuntimeError, match="released"):
        csm.render(scene, light, camera, width=800, height=600)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"shadow_cascades": 0}, "shadow_cascades"),
        ({"shadow_split_lambda": 1.1}, "shadow_split_lambda"),
        ({"ssao_samples": 12}, "ssao_samples"),
        ({"bloom_levels": 0}, "bloom_levels"),
        ({"max_decals": -1}, "max_decals"),
    ],
)
def test_renderer2_settings_reject_invalid_quality_values(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Renderer2Settings(**changes)
