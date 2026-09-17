from __future__ import annotations

import pytest

from swirengine.render_submission18 import (
    MaterialKey,
    MaterialSubmissionQueue,
    PipelineStateCache,
    PipelineStateKey,
    RenderSubmissionError,
)


def _pipe(name: str, *, blend: str = "opaque") -> PipelineStateKey:
    return PipelineStateKey(shader=name, blend_mode=blend)


def _mat(name: str) -> MaterialKey:
    return MaterialKey(name)


def test_keys_are_normalized_and_fingerprints_stable() -> None:
    first = PipelineStateKey(" lit ", variants=(("B", "2"), ("A", "1")))
    second = PipelineStateKey("lit", variants=(("A", "1"), ("B", "2")))

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert MaterialKey("hero", ("albedo", "normal")).fingerprint == MaterialKey(
        "hero", ("albedo", "normal")
    ).fingerprint


def test_reorderable_runs_reduce_state_switches() -> None:
    queue = MaterialSubmissionQueue()
    pipeline_a, pipeline_b = _pipe("a"), _pipe("b")
    material_a, material_b = _mat("a"), _mat("b")
    for index in range(8):
        queue.submit(
            f"draw-{index}",
            pipeline_a if index % 2 == 0 else pipeline_b,
            material_a if index % 2 == 0 else material_b,
            f"mesh-{index}",
        )

    plan = queue.compile()

    assert plan.diagnostics.authored_pipeline_switches == 7
    assert plan.diagnostics.compiled_pipeline_switches == 1
    assert plan.diagnostics.pipeline_switches_saved == 6
    assert len(plan.draws) == 8


def test_preserve_order_draw_is_a_barrier() -> None:
    queue = MaterialSubmissionQueue()
    pipeline_a, pipeline_b = _pipe("a"), _pipe("b")
    material = _mat("m")
    queue.submit("left-b", pipeline_b, material, "mesh-1")
    queue.submit("left-a", pipeline_a, material, "mesh-2")
    barrier = queue.submit(
        "transparent",
        _pipe("alpha", blend="alpha"),
        material,
        "mesh-3",
        preserve_order=True,
    )
    queue.submit("right-b", pipeline_b, material, "mesh-4")
    queue.submit("right-a", pipeline_a, material, "mesh-5")

    plan = queue.compile()
    draw_ids = [draw.draw_id for draw in plan.draws]

    assert draw_ids.index(barrier.draw_id) == 2
    assert set(draw_ids[:2]) == {"left-a", "left-b"}
    assert set(draw_ids[3:]) == {"right-a", "right-b"}
    assert plan.diagnostics.ordered_draws == 1
    assert plan.diagnostics.sort_segments == 2


def test_layer_is_primary_inside_reorderable_segment() -> None:
    queue = MaterialSubmissionQueue()
    pipeline, material = _pipe("basic"), _mat("basic")
    queue.submit("layer-5", pipeline, material, "a", layer=5)
    queue.submit("layer-1", pipeline, material, "b", layer=1)

    assert [draw.draw_id for draw in queue.compile().draws] == ["layer-1", "layer-5"]


def test_draw_limit_is_explicit() -> None:
    queue = MaterialSubmissionQueue(max_draws=1)
    queue.submit("one", _pipe("x"), _mat("x"), "mesh")

    with pytest.raises(RenderSubmissionError) as exc:
        queue.submit("two", _pipe("x"), _mat("x"), "mesh")

    assert exc.value.code == "draw-limit"


def test_plan_fingerprint_is_deterministic() -> None:
    def build() -> str:
        queue = MaterialSubmissionQueue()
        for index in range(10):
            queue.submit(
                str(index),
                _pipe(str(index % 3)),
                _mat(str(index % 2)),
                f"mesh-{index}",
            )
        return queue.compile().fingerprint

    assert build() == build()


def test_cache_hits_and_lru_eviction_are_deterministic() -> None:
    created: list[str] = []
    destroyed: list[str] = []

    def create(key: PipelineStateKey) -> str:
        pipeline = f"gpu:{key.shader}:{len(created)}"
        created.append(pipeline)
        return pipeline

    cache = PipelineStateCache(create=create, destroy=destroyed.append, max_entries=2)
    key_a, key_b, key_c = _pipe("a"), _pipe("b"), _pipe("c")
    pipeline_a = cache.get_or_create(key_a)
    pipeline_b = cache.get_or_create(key_b)
    assert cache.get_or_create(key_a) == pipeline_a
    cache.get_or_create(key_c)

    assert destroyed == [pipeline_b]
    diagnostics = cache.diagnostics()
    assert diagnostics.hits == 1
    assert diagnostics.misses == 3
    assert diagnostics.creates == 3
    assert diagnostics.evictions == 1
    assert diagnostics.resident_entries == 2


def test_create_failure_does_not_mutate_residency() -> None:
    good = _pipe("good")
    bad = _pipe("bad")

    def create(key: PipelineStateKey) -> str:
        if key == bad:
            raise RuntimeError("compile error")
        return key.shader

    cache = PipelineStateCache(create=create, destroy=lambda _: None, max_entries=2)
    assert cache.get_or_create(good) == "good"

    with pytest.raises(RenderSubmissionError) as exc:
        cache.get_or_create(bad)

    assert exc.value.code == "pipeline-create-failed"
    assert cache.diagnostics().resident_entries == 1
    assert cache.get_or_create(good) == "good"


def test_eviction_failure_keeps_victim_cached_and_rolls_back_candidate() -> None:
    destroyed: list[str] = []

    def destroy(value: str) -> None:
        destroyed.append(value)
        if value == "a":
            raise RuntimeError("device refused")

    cache = PipelineStateCache(
        create=lambda key: key.shader,
        destroy=destroy,
        max_entries=1,
    )
    key_a, key_b = _pipe("a"), _pipe("b")
    assert cache.get_or_create(key_a) == "a"

    with pytest.raises(RenderSubmissionError) as exc:
        cache.get_or_create(key_b)

    assert exc.value.code == "pipeline-evict-failed"
    assert cache.diagnostics().resident_entries == 1
    assert cache.get_or_create(key_a) == "a"
    assert destroyed == ["a", "b"]


def test_shader_invalidation_and_close() -> None:
    destroyed: list[str] = []
    cache = PipelineStateCache(
        create=lambda key: key.fingerprint,
        destroy=destroyed.append,
        max_entries=4,
    )
    lit_1 = PipelineStateKey("lit", variants=(("MODE", "1"),))
    lit_2 = PipelineStateKey("lit", variants=(("MODE", "2"),))
    ui = _pipe("ui")
    for key in (lit_1, lit_2, ui):
        cache.get_or_create(key)

    assert cache.invalidate_shader("lit") == 2
    assert cache.diagnostics().resident_entries == 1
    cache.close()

    assert cache.closed
    assert cache.diagnostics().resident_entries == 0
    with pytest.raises(RenderSubmissionError) as exc:
        cache.get_or_create(ui)
    assert exc.value.code == "cache-closed"


def test_prepare_resolves_compiled_plan_and_reuses_states() -> None:
    created: list[str] = []
    cache = PipelineStateCache(
        create=lambda key: created.append(key.shader) or f"state:{key.shader}",
        destroy=lambda _: None,
        max_entries=8,
    )
    queue = MaterialSubmissionQueue()
    pipeline = _pipe("shared")
    for index in range(5):
        queue.submit(str(index), pipeline, _mat(str(index)), f"mesh-{index}")

    prepared = cache.prepare(queue.compile())

    assert [state for _, state in prepared] == ["state:shared"] * 5
    assert created == ["shared"]
    assert cache.diagnostics().hits == 4


def test_validation_rejects_unstable_inputs() -> None:
    with pytest.raises(ValueError):
        PipelineStateKey("x", variants=(("A", "1"), ("A", "2")))
    with pytest.raises(TypeError):
        MaterialSubmissionQueue(max_draws=True)
    with pytest.raises(TypeError):
        MaterialSubmissionQueue().submit(
            "draw",
            _pipe("x"),
            _mat("m"),
            "mesh",
            preserve_order=1,  # type: ignore[arg-type]
        )
