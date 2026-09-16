from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.lights import DirectionalLight3D
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


def test_practical_cascade_splits_are_monotonic_and_cover_far_plane() -> None:
    splits = practical_cascade_splits(0.1, 100.0, 4, 0.72)

    assert len(splits) == 4
    assert all(a < b for a, b in zip(splits, splits[1:]))
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


def test_renderer2_planner_omits_shadow_pass_without_directional_light() -> None:
    scene = SceneStub([Cube3D(position=Vec3(0.0, 0.0, -4.0))])

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
