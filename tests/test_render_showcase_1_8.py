from __future__ import annotations

from types import SimpleNamespace

import pytest

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.render_resources18 import (
    RenderResourceDescriptor,
    TransientRenderResourcePool,
)
from swirengine.render_showcase18 import (
    RenderShowcaseError,
    RenderShowcaseSettings,
    RenderShowcaseUpload,
    run_render_showcase,
)
from swirengine.render_uploads18 import TextureUploadQueue
from swirengine.renderer2_bridge18 import Renderer2CompatibilityBridge


class GraphRenderer:
    def __init__(self, mode: str, *, fail_calls: tuple[int, ...] = ()):
        self.mode = mode
        self.width = 1280
        self.height = 720
        self.graph_calls = 0
        self.fail_calls = set(fail_calls)

    def render_graph18(self, frame, scene, *, camera=None, clear_color=None):
        del frame, scene, camera, clear_color
        self.graph_calls += 1
        if self.graph_calls in self.fail_calls:
            raise RuntimeError("injected graph backend failure")


def scene(*objects):
    return SimpleNamespace(objects=list(objects))


def texture_descriptor() -> RenderResourceDescriptor:
    return RenderResourceDescriptor(
        kind="texture",
        format="rgba8",
        width=8,
        height=8,
        size_bytes=8 * 8 * 4,
    )


def test_settings_and_upload_specs_validate_bounds():
    with pytest.raises(ValueError, match="frames"):
        RenderShowcaseSettings(frames=0)
    with pytest.raises(TypeError, match="integer"):
        RenderShowcaseSettings(max_consecutive_failures=True)
    with pytest.raises(ValueError, match="texture"):
        RenderShowcaseUpload(
            "buffer",
            RenderResourceDescriptor(
                kind="buffer",
                format="raw",
                width=1,
                height=1,
                size_bytes=4,
            ),
            b"data",
        )


def test_integrated_soak_contains_injected_failures_and_recovers_next_frame():
    resource_create_calls = 0

    def create_resource(descriptor):
        nonlocal resource_create_calls
        resource_create_calls += 1
        if resource_create_calls == 1:
            raise RuntimeError("injected allocation failure")
        return {"bytes": descriptor.size_bytes, "serial": resource_create_calls}

    pool = TransientRenderResourcePool(
        create=create_resource,
        destroy=lambda resource: None,
        max_resources=2,
        max_bytes=1024,
    )

    submit_calls = 0

    def submit(upload):
        nonlocal submit_calls
        submit_calls += 1
        if submit_calls == 1:
            raise RuntimeError("injected upload failure")

    queue = TextureUploadQueue(
        submit=submit,
        max_pending_uploads=16,
        max_pending_bytes=4096,
        max_uploads_per_flush=16,
        max_bytes_per_flush=4096,
        max_resident_textures=2,
        max_resident_bytes=1024,
    )
    descriptor = texture_descriptor()
    renderer = GraphRenderer("2d", fail_calls=(1,))
    report = run_render_showcase(
        Renderer2CompatibilityBridge(renderer),
        lambda frame: scene(Rectangle2D(frame, 0, 8, 8)),
        settings=RenderShowcaseSettings(frames=8, max_consecutive_failures=2),
        resource_pool=pool,
        resource_descriptors=(descriptor,),
        upload_queue=queue,
        uploads=(RenderShowcaseUpload("atlas", descriptor, bytes(256)),),
    )

    assert report.frames_attempted == 8
    assert report.clean_frames == 7
    assert report.rendered_frames == 7
    assert report.graph_backend_frames == 7
    assert report.allocation_failures == 1
    assert report.upload_failures == 1
    assert report.render_failures == 1
    assert report.recoveries == 1
    assert report.max_consecutive_failures == 1
    assert report.resource_acquires == 7
    assert report.resource_reuses == 6
    assert report.upload_submissions == 1
    assert report.duplicate_upload_skips == 7
    assert [(event.frame, event.stage) for event in report.retained_failures] == [
        (0, "allocation"),
        (0, "upload"),
        (0, "render"),
    ]
    assert len(report.workload_fingerprint) == 64
    assert len(report.fingerprint()) == 64
    assert pool.diagnostics().leased_resources == 0


def test_3d_showcase_uses_real_renderer2_planning_and_camera_path():
    renderer = GraphRenderer("3d")
    report = run_render_showcase(
        Renderer2CompatibilityBridge(renderer),
        lambda frame: scene(Cube3D(x=float(frame % 3))),
        camera_factory=lambda frame: Camera3D(),
        settings=RenderShowcaseSettings(frames=12),
    )

    assert report.clean_frames == 12
    assert report.rendered_frames == 12
    assert report.graph_backend_frames == 12
    assert report.render_failures == 0
    assert report.bridge_diagnostics["last_graph_passes"] > 0


def test_report_is_deterministic_for_identical_workload():
    def run_once():
        descriptor = texture_descriptor()
        pool = TransientRenderResourcePool(
            create=lambda item: ("resource", item.size_bytes),
            destroy=lambda resource: None,
            max_resources=2,
            max_bytes=1024,
        )
        queue = TextureUploadQueue(
            submit=lambda upload: None,
            max_pending_uploads=8,
            max_pending_bytes=4096,
            max_uploads_per_flush=8,
            max_bytes_per_flush=4096,
            max_resident_textures=2,
            max_resident_bytes=1024,
        )
        report = run_render_showcase(
            Renderer2CompatibilityBridge(GraphRenderer("2d")),
            lambda frame: scene(Rectangle2D(frame % 4, frame % 3, 8, 8)),
            settings=RenderShowcaseSettings(frames=20),
            resource_pool=pool,
            resource_descriptors=(descriptor,),
            upload_queue=queue,
            uploads=(RenderShowcaseUpload("atlas", descriptor, bytes(256)),),
        )
        return report

    left = run_once()
    right = run_once()
    assert left.portable() == right.portable()
    assert left.fingerprint() == right.fingerprint()


def test_failure_history_is_bounded_under_long_fault_sequence():
    renderer = GraphRenderer("2d", fail_calls=tuple(range(1, 9)))
    report = run_render_showcase(
        Renderer2CompatibilityBridge(renderer),
        lambda frame: scene(Rectangle2D(0, 0, 4, 4)),
        settings=RenderShowcaseSettings(
            frames=8,
            max_consecutive_failures=8,
            retained_failure_events=3,
        ),
    )
    assert report.render_failures == 8
    assert report.max_consecutive_failures == 8
    assert len(report.retained_failures) == 3
    assert [event.frame for event in report.retained_failures] == [5, 6, 7]


def test_failure_budget_stops_run_instead_of_hiding_persistent_backend_failure():
    renderer = GraphRenderer("2d", fail_calls=(1, 2, 3, 4))
    with pytest.raises(RenderShowcaseError) as exc:
        run_render_showcase(
            Renderer2CompatibilityBridge(renderer),
            lambda frame: scene(Rectangle2D(0, 0, 4, 4)),
            settings=RenderShowcaseSettings(frames=8, max_consecutive_failures=2),
        )
    assert exc.value.code == "failure-budget-exceeded"


def test_resource_pool_failure_does_not_leave_partial_leases():
    descriptor = texture_descriptor()
    calls = 0

    def create_resource(item):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second allocation fails")
        return calls

    pool = TransientRenderResourcePool(
        create=create_resource,
        destroy=lambda resource: None,
        max_resources=4,
        max_bytes=4096,
    )
    other = RenderResourceDescriptor(
        kind="texture",
        format="rgba16f",
        width=8,
        height=8,
        size_bytes=512,
    )
    report = run_render_showcase(
        Renderer2CompatibilityBridge(GraphRenderer("2d")),
        lambda frame: scene(Rectangle2D(0, 0, 4, 4)),
        settings=RenderShowcaseSettings(frames=2, max_consecutive_failures=2),
        resource_pool=pool,
        resource_descriptors=(descriptor, other),
    )
    assert report.allocation_failures == 1
    assert pool.diagnostics().leased_resources == 0


def test_argument_contract_rejects_disconnected_resource_and_upload_workloads():
    bridge = Renderer2CompatibilityBridge(GraphRenderer("2d"))
    descriptor = texture_descriptor()
    with pytest.raises(ValueError, match="resource_pool"):
        run_render_showcase(
            bridge,
            lambda frame: scene(),
            resource_descriptors=(descriptor,),
        )
    with pytest.raises(ValueError, match="upload_queue"):
        run_render_showcase(
            bridge,
            lambda frame: scene(),
            uploads=(RenderShowcaseUpload("atlas", descriptor, bytes(256)),),
        )
