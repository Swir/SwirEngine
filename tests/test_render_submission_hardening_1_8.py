from __future__ import annotations

import pytest

from swirengine.render_submission18 import (
    MaterialKey,
    MaterialSubmissionQueue,
    PipelineStateCache,
    PipelineStateKey,
    RenderSubmissionError,
)


def _pipe(name: str, **kwargs: object) -> PipelineStateKey:
    return PipelineStateKey(name, **kwargs)


def _mat(name: str) -> MaterialKey:
    return MaterialKey(name)


def test_order_barriers_preserve_authored_barrier_sequence_exactly() -> None:
    queue = MaterialSubmissionQueue()
    barrier_ids: list[str] = []
    for index in range(30):
        strict = index in {5, 11, 18, 29}
        draw = queue.submit(
            f"draw-{index}",
            _pipe(f"shader-{index % 5}"),
            _mat(f"mat-{index % 7}"),
            f"mesh-{index}",
            preserve_order=strict,
        )
        if strict:
            barrier_ids.append(draw.draw_id)

    plan = queue.compile()
    positions = [
        next(i for i, draw in enumerate(plan.draws) if draw.draw_id == draw_id)
        for draw_id in barrier_ids
    ]

    assert positions == [5, 11, 18, 29]


def test_sort_is_stable_when_state_keys_tie() -> None:
    queue = MaterialSubmissionQueue()
    pipeline = _pipe("same")
    material = _mat("same")
    for name in ("z", "a", "m", "b"):
        queue.submit(name, pipeline, material, "mesh", sort_depth=0)

    assert [draw.draw_id for draw in queue.compile().draws] == ["z", "a", "m", "b"]


def test_pipeline_key_fingerprint_covers_render_state() -> None:
    base = _pipe("lit")
    variants = [
        _pipe("lit", blend_mode="alpha"),
        _pipe("lit", depth_mode="disabled"),
        _pipe("lit", cull_mode="none"),
        _pipe("lit", topology="lines"),
        _pipe("lit", render_target="hdr"),
        _pipe("lit", samples=4),
        _pipe("lit", vertex_layout="skinned"),
        _pipe("lit", variants=(("SKINNED", "1"),)),
    ]

    assert len({base.fingerprint, *(item.fingerprint for item in variants)}) == len(variants) + 1


def test_cache_capacity_never_exceeds_hard_bound() -> None:
    cache = PipelineStateCache(
        create=lambda key: key.shader,
        destroy=lambda _: None,
        max_entries=3,
    )
    for index in range(50):
        cache.get_or_create(_pipe(f"shader-{index}"))
        assert cache.diagnostics().resident_entries <= 3

    assert cache.diagnostics().peak_entries == 3
    assert cache.diagnostics().evictions == 47


def test_partial_shader_invalidation_keeps_failed_entry_live() -> None:
    failed_pipeline: object | None = None
    objects: dict[PipelineStateKey, object] = {}

    def create(key: PipelineStateKey) -> object:
        pipeline = object()
        objects[key] = pipeline
        return pipeline

    def destroy(pipeline: object) -> None:
        if pipeline is failed_pipeline:
            raise RuntimeError("still in flight")

    cache = PipelineStateCache(create=create, destroy=destroy, max_entries=8)
    first = _pipe("lit", variants=(("A", "1"),))
    second = _pipe("lit", variants=(("B", "1"),))
    ui = _pipe("ui")
    for key in (first, second, ui):
        cache.get_or_create(key)
    failed_pipeline = objects[second]

    with pytest.raises(RenderSubmissionError) as exc:
        cache.invalidate_shader("lit")

    assert exc.value.code == "pipeline-invalidate-failed"
    assert cache.diagnostics().resident_entries == 2
    assert cache.get_or_create(second) is failed_pipeline
    assert cache.get_or_create(ui) is objects[ui]


def test_close_failure_is_retryable_and_does_not_mark_closed() -> None:
    failure = {"active": True}

    def destroy(_: str) -> None:
        if failure["active"]:
            raise RuntimeError("gpu busy")

    cache = PipelineStateCache(
        create=lambda key: key.shader,
        destroy=destroy,
        max_entries=2,
    )
    cache.get_or_create(_pipe("a"))

    with pytest.raises(RenderSubmissionError) as exc:
        cache.close()

    assert exc.value.code == "pipeline-close-failed"
    assert not cache.closed
    assert cache.diagnostics().resident_entries == 1
    failure["active"] = False
    cache.close()
    assert cache.closed
    assert cache.diagnostics().resident_entries == 0


def test_clear_continues_after_failure_and_reports_remaining_entries() -> None:
    failed = {"b"}

    def destroy(value: str) -> None:
        if value in failed:
            raise RuntimeError(value)

    cache = PipelineStateCache(
        create=lambda key: key.shader,
        destroy=destroy,
        max_entries=4,
    )
    for name in ("a", "b", "c"):
        cache.get_or_create(_pipe(name))

    with pytest.raises(RenderSubmissionError) as exc:
        cache.clear()

    assert exc.value.code == "pipeline-clear-failed"
    assert cache.diagnostics().resident_entries == 1
    assert cache.get_or_create(_pipe("b")) == "b"
    failed.clear()
    assert cache.clear() == 1


def test_prepare_stops_on_create_failure_without_reordering_plan() -> None:
    queue = MaterialSubmissionQueue()
    for shader in ("a", "bad", "c"):
        queue.submit(
            shader,
            _pipe(shader),
            _mat(shader),
            f"mesh-{shader}",
            preserve_order=True,
        )
    plan = queue.compile()

    def create(key: PipelineStateKey) -> str:
        if key.shader == "bad":
            raise RuntimeError("compile")
        return key.shader

    cache = PipelineStateCache(create=create, destroy=lambda _: None, max_entries=8)

    with pytest.raises(RenderSubmissionError) as exc:
        cache.prepare(plan)

    assert exc.value.code == "pipeline-create-failed"
    assert [draw.draw_id for draw in plan.draws] == ["a", "bad", "c"]
    assert cache.diagnostics().resident_entries == 1
