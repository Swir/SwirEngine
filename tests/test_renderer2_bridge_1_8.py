from types import SimpleNamespace

import pytest

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.instancing import InstancedCube3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D, Sprite2D, Text2D
from swirengine.render_quality18 import DynamicQualityController, RenderQualityStep
from swirengine.renderer2_bridge18 import (
    Renderer2BridgeCompiler,
    Renderer2BridgeError,
    Renderer2BridgeSettings,
    Renderer2CompatibilityBridge,
)


class FakeRenderer:
    def __init__(self, mode="2d", width=1280, height=720):
        self.mode = mode
        self.width = width
        self.height = height
        self.calls = []

    def render(self, scene, *, camera=None, clear_color=(0.0, 0.0, 0.0, 1.0)):
        self.calls.append((scene, camera, clear_color))


class GraphRenderer(FakeRenderer):
    def __init__(self, mode="3d", width=1280, height=720):
        super().__init__(mode, width, height)
        self.graph_calls = []

    def render_graph18(self, frame, scene, *, camera=None, clear_color=(0.0, 0.0, 0.0, 1.0)):
        self.graph_calls.append((frame, scene, camera, clear_color))


def scene(*objects):
    return SimpleNamespace(objects=list(objects))


def test_2d_bridge_preserves_layer_order_and_sprite_batching(tmp_path):
    texture = tmp_path / "atlas.png"
    renderer = FakeRenderer("2d")
    frame = Renderer2BridgeCompiler().prepare(
        renderer,
        scene(
            Rectangle2D(0, 0, 16, 16, layer=3),
            Sprite2D(texture, layer=1),
            Sprite2D(texture, x=10, layer=1),
            Text2D("HUD", layer=2, screen_space=True),
        ),
    )

    assert [(run.kind, run.count, run.layer) for run in frame.runs_2d] == [
        ("sprite_batch", 2, 1),
        ("text", 1, 2),
        ("rectangle", 1, 3),
    ]
    assert all(len(run.content_fingerprint) == 64 for run in frame.runs_2d)
    assert frame.graph.diagnostics.active_passes == 3
    assert frame.graph.passes == (
        "stage_0000_sprite_batch",
        "stage_0001_text",
        "stage_0002_rectangle",
    )


def test_2d_bridge_skips_disabled_and_invisible_objects():
    hidden = Rectangle2D(0, 0, 10, 10, visible=False)
    disabled = Text2D("off", enabled=False)
    frame = Renderer2BridgeCompiler().prepare(FakeRenderer("2d"), scene(hidden, disabled))
    assert frame.runs_2d == ()
    assert frame.graph.passes == ("stage_0000_clear",)


def test_3d_bridge_uses_renderer2_planner_without_gpu_context():
    renderer = FakeRenderer("3d", 1920, 1080)
    frame = Renderer2BridgeCompiler().prepare(renderer, scene(Cube3D()), camera=Camera3D())
    planned = [item.name for item in frame.renderer2_plan.passes]
    assert "depth_prepass" in planned
    assert "opaque" in planned
    assert "hdr_resolve" in planned
    assert frame.graph.diagnostics.active_passes == len(planned)


def test_instancing_is_accounted_for_in_3d_compatibility_plan():
    batch = InstancedCube3D()
    batch.add_cube()
    batch.add_cube(visible=False)
    batch.add_cube()
    frame = Renderer2BridgeCompiler().prepare(
        FakeRenderer("3d"), scene(Cube3D(), batch), camera=Camera3D()
    )
    assert frame.instanced_batches == 1
    assert frame.instanced_instances == 2
    assert frame.graph.passes[-1].endswith("instancing_compat")


def test_dynamic_quality_step_is_carried_without_mutating_legacy_dimensions():
    quality = DynamicQualityController(
        (RenderQualityStep("native", 1.0), RenderQualityStep("balanced", 0.75, 0.8)),
        initial_step="balanced",
    )
    renderer = FakeRenderer("2d", 1600, 900)
    frame = Renderer2BridgeCompiler(quality=quality).prepare(renderer, scene())
    assert frame.quality_step.name == "balanced"
    assert frame.quality_step.resolution_scale == 0.75
    assert (frame.width, frame.height) == (1600, 900)


def test_graph_backend_receives_compiled_frame_and_legacy_render_is_not_called():
    renderer = GraphRenderer("3d")
    world = scene(Cube3D())
    camera = Camera3D()
    result = Renderer2CompatibilityBridge(renderer).render(world, camera=camera)
    assert result.execution == "graph-backend"
    assert len(renderer.graph_calls) == 1
    assert renderer.calls == []
    assert renderer.graph_calls[0][0] is result.frame
    assert result.frame.graph_backend_available is True


def test_existing_renderer_uses_graph_validated_compatibility_execution_once():
    renderer = FakeRenderer("2d")
    world = scene(Rectangle2D(0, 0, 20, 20))
    bridge = Renderer2CompatibilityBridge(renderer)
    result = bridge.render(world)
    assert result.execution == "graph-compat"
    assert len(renderer.calls) == 1
    diagnostics = bridge.diagnostics()
    assert diagnostics.prepared_frames == 1
    assert diagnostics.graph_compat_frames == 1
    assert diagnostics.last_graph_passes == 1


def test_explicit_fallback_is_used_when_graph_preparation_fails():
    renderer = FakeRenderer("unsupported")
    bridge = Renderer2CompatibilityBridge(renderer)
    result = bridge.render(scene())
    assert result.execution == "fallback"
    assert result.frame is None
    assert "renderer mode" in result.fallback_reason
    assert len(renderer.calls) == 1
    assert bridge.diagnostics().prepare_failures == 1


def test_fallback_can_be_disabled_for_strict_creator_workflows():
    renderer = FakeRenderer("unsupported")
    bridge = Renderer2CompatibilityBridge(
        renderer,
        settings=Renderer2BridgeSettings(fallback_on_prepare_error=False),
    )
    with pytest.raises(Renderer2BridgeError) as exc:
        bridge.render(scene())
    assert exc.value.code == "unsupported-mode"
    assert renderer.calls == []


def test_native_graph_requirement_can_fall_back_explicitly():
    renderer = FakeRenderer("2d")
    bridge = Renderer2CompatibilityBridge(
        renderer,
        settings=Renderer2BridgeSettings(allow_compat_execution=False),
    )
    result = bridge.render(scene(Rectangle2D(0, 0, 10, 10)))
    assert result.execution == "fallback"
    assert result.frame is not None
    assert result.fallback_reason == "native render_graph18 backend unavailable"
    assert len(renderer.calls) == 1


def test_2d_run_bound_fails_before_backend_submission(tmp_path):
    objects = [
        Sprite2D(tmp_path / f"texture-{index}.png", layer=index)
        for index in range(3)
    ]
    renderer = FakeRenderer("2d")
    compiler = Renderer2BridgeCompiler(settings=Renderer2BridgeSettings(max_2d_runs=2))
    with pytest.raises(Renderer2BridgeError) as exc:
        compiler.prepare(renderer, scene(*objects))
    assert exc.value.code == "2d-run-limit"


def test_frame_fingerprint_is_deterministic_for_same_submission_contract(tmp_path):
    texture = tmp_path / "atlas.png"
    world = scene(Sprite2D(texture), Sprite2D(texture), Text2D("score", layer=1))
    renderer = FakeRenderer("2d")
    compiler = Renderer2BridgeCompiler()
    left = compiler.prepare(renderer, world)
    right = compiler.prepare(renderer, world)
    assert left.fingerprint == right.fingerprint
    assert left.graph.fingerprint == right.graph.fingerprint
    changed = compiler.prepare(
        renderer, scene(Text2D("score", layer=1), Rectangle2D(0, 0, 8, 8, layer=2))
    )
    assert changed.fingerprint != left.fingerprint


def test_frame_fingerprint_tracks_text_and_texture_identity(tmp_path):
    renderer = FakeRenderer("2d")
    compiler = Renderer2BridgeCompiler()

    text_left = compiler.prepare(renderer, scene(Text2D("score", layer=1)))
    text_right = compiler.prepare(renderer, scene(Text2D("health", layer=1)))
    assert text_left.graph.fingerprint == text_right.graph.fingerprint
    assert text_left.fingerprint != text_right.fingerprint

    texture_left = compiler.prepare(renderer, scene(Sprite2D(tmp_path / "a.png", layer=1)))
    texture_right = compiler.prepare(renderer, scene(Sprite2D(tmp_path / "b.png", layer=1)))
    assert texture_left.graph.fingerprint == texture_right.graph.fingerprint
    assert texture_left.fingerprint != texture_right.fingerprint
    assert "a.png" not in str(texture_left.portable())


def test_invalid_renderer_dimensions_are_contained_by_legacy_fallback():
    renderer = FakeRenderer("2d", width=0, height=720)
    bridge = Renderer2CompatibilityBridge(renderer)
    result = bridge.render(scene())
    assert result.execution == "fallback"
    assert result.frame is None
    assert len(renderer.calls) == 1
