from __future__ import annotations

import threading

import pytest

from swirengine.shader_cache17 import (
    PreparedShaderMaterial,
    ShaderMaterialPreparationCache,
    ShaderMaterialRequestState,
    ShaderMaterialSource,
)

VERTEX = "#version 330\nvoid main() { gl_Position = vec4(0.0); }"
FRAGMENT = "#version 330\nout vec4 color; void main() { color = vec4(1.0); }"


def _stages(fragment: str = FRAGMENT) -> dict[str, str]:
    return {"vertex": VERTEX, "fragment": fragment}


def _finish(cache: ShaderMaterialPreparationCache, request_id: int):
    cache.wait_workers(timeout=2.0)
    outcomes = cache.poll(max_items=32)
    match = [outcome for outcome in outcomes if outcome.request_id == request_id]
    assert len(match) == 1
    return match[0]


def test_source_fingerprint_is_deterministic_and_sensitive() -> None:
    first = ShaderMaterialSource.capture(
        {"Vertex": VERTEX, "fragment": FRAGMENT},
        defines={"QUALITY": 2, "FOG": True},
        material={"roughness": 0.5, "tags": ["world", "opaque"]},
    )
    second = ShaderMaterialSource.capture(
        {"fragment": FRAGMENT, "vertex": VERTEX},
        defines={"FOG": True, "QUALITY": 2},
        material={"tags": ["world", "opaque"], "roughness": 0.5},
    )
    changed = ShaderMaterialSource.capture(
        _stages(FRAGMENT + "\n// changed"),
        defines={"FOG": True, "QUALITY": 2},
        material={"tags": ["world", "opaque"], "roughness": 0.5},
    )

    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint
    assert first.stage_names == ("fragment", "vertex")


def test_preprocess_runs_on_worker_and_finalizer_runs_on_owner_thread() -> None:
    owner_thread = threading.get_ident()
    worker_threads: list[int] = []
    finalizer_threads: list[int] = []
    preprocess_calls = 0

    def preprocess(source, context):
        nonlocal preprocess_calls
        preprocess_calls += 1
        worker_threads.append(threading.get_ident())
        context.raise_if_cancelled()
        return {
            name: text + "\n// prepared"
            for name, text in source.stage_mapping().items()
        }

    def finalize(prepared: PreparedShaderMaterial):
        finalizer_threads.append(threading.get_ident())
        return prepared.stage_mapping()["fragment"]

    cache = ShaderMaterialPreparationCache(max_workers=1)
    try:
        first = cache.submit(_stages(), preprocess=preprocess, finalize=finalize)
        first_result = _finish(cache, first.request_id)
        second = cache.submit(_stages(), preprocess=preprocess, finalize=finalize)
        second_result = _finish(cache, second.request_id)

        assert first_result.successful
        assert not first_result.cache_hit
        assert second_result.successful
        assert second_result.cache_hit
        assert preprocess_calls == 1
        assert worker_threads and all(thread != owner_thread for thread in worker_threads)
        assert finalizer_threads == [owner_thread, owner_thread]
        assert first_result.value.endswith("// prepared")
        assert second_result.value == first_result.value
    finally:
        cache.shutdown()


def test_poll_rejects_non_owner_thread_without_consuming_completion() -> None:
    cache = ShaderMaterialPreparationCache(max_workers=1)
    try:
        request = cache.submit(_stages(), finalize=lambda prepared: prepared.source_fingerprint)
        cache.wait_workers(timeout=2.0)
        errors: list[BaseException] = []

        def wrong_thread_poll() -> None:
            try:
                cache.poll()
            except BaseException as exc:  # noqa: BLE001 - test captures the public failure.
                errors.append(exc)

        thread = threading.Thread(target=wrong_thread_poll)
        thread.start()
        thread.join(timeout=2.0)

        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)
        result = cache.poll()[0]
        assert result.request_id == request.request_id
        assert result.successful
    finally:
        cache.shutdown()


def test_invalidation_marks_matching_inflight_preparation_stale() -> None:
    started = threading.Event()
    release = threading.Event()
    finalized: list[str] = []

    def preprocess(source, context):
        started.set()
        assert release.wait(timeout=2.0)
        context.raise_if_cancelled()
        return source.stage_mapping()

    cache = ShaderMaterialPreparationCache(max_workers=1)
    try:
        request = cache.submit(
            _stages(),
            preprocess=preprocess,
            finalize=lambda prepared: finalized.append(prepared.source_fingerprint),
        )
        assert started.wait(timeout=2.0)
        assert cache.invalidate(request.fingerprint) == 0
        release.set()
        result = _finish(cache, request.request_id)

        assert result.state is ShaderMaterialRequestState.STALE
        assert result.error_type == "ShaderPreparationInvalidated"
        assert finalized == []
        diagnostics = cache.diagnostics()
        assert diagnostics.stale_total == 1
        assert diagnostics.invalidations_total == 1
        assert diagnostics.cached_entries == 0
    finally:
        release.set()
        cache.shutdown()


def test_cancel_after_worker_completion_prevents_finalization() -> None:
    finalized: list[str] = []
    cache = ShaderMaterialPreparationCache(max_workers=1)
    try:
        request = cache.submit(
            _stages(),
            finalize=lambda prepared: finalized.append(prepared.source_fingerprint),
        )
        cache.wait_workers(timeout=2.0)
        assert cache.cancel(request.request_id)
        result = cache.poll()[0]

        assert result.state is ShaderMaterialRequestState.CANCELLED
        assert finalized == []
        assert cache.diagnostics().cancelled_total == 1
    finally:
        cache.shutdown()


def test_finalizer_failure_is_isolated_and_prepared_data_stays_reusable() -> None:
    cache = ShaderMaterialPreparationCache(max_workers=1)
    try:
        failing = cache.submit(
            _stages(),
            finalize=lambda prepared: (_ for _ in ()).throw(RuntimeError("compile failed")),
        )
        failed = _finish(cache, failing.request_id)
        assert failed.state is ShaderMaterialRequestState.FAILED
        assert failed.error_type == "RuntimeError"
        assert failed.error_message == "compile failed"

        succeeding = cache.submit(
            _stages(),
            finalize=lambda prepared: prepared.source_fingerprint,
        )
        completed = _finish(cache, succeeding.request_id)
        assert completed.successful
        assert completed.cache_hit
        assert completed.value == succeeding.fingerprint
        diagnostics = cache.diagnostics()
        assert diagnostics.failed_total == 1
        assert diagnostics.completed_total == 1
    finally:
        cache.shutdown()


def test_cache_has_deterministic_bounded_fifo_eviction() -> None:
    cache = ShaderMaterialPreparationCache(max_workers=1, max_cache_entries=2)
    try:
        requests = []
        for index in range(3):
            request = cache.submit(
                _stages(FRAGMENT + f"\n// variant {index}"),
                finalize=lambda prepared: prepared.source_fingerprint,
            )
            requests.append(request)
            assert _finish(cache, request.request_id).successful

        assert cache.diagnostics().cached_entries == 2
        assert cache.diagnostics().cache_evictions_total == 1

        repeated = cache.submit(
            _stages(FRAGMENT + "\n// variant 0"),
            finalize=lambda prepared: prepared.source_fingerprint,
        )
        repeated_result = _finish(cache, repeated.request_id)
        assert repeated_result.successful
        assert not repeated_result.cache_hit
        assert cache.diagnostics().cache_evictions_total == 2
        assert requests[0].fingerprint == repeated.fingerprint
    finally:
        cache.shutdown()


def test_preprocessor_cannot_change_stage_set() -> None:
    cache = ShaderMaterialPreparationCache(max_workers=1)
    try:
        request = cache.submit(
            _stages(),
            preprocess=lambda source, context: {"vertex": VERTEX},
            finalize=lambda prepared: prepared,
        )
        result = _finish(cache, request.request_id)
        assert result.state is ShaderMaterialRequestState.FAILED
        assert result.error_type == "ValueError"
        assert "preserve" in (result.error_message or "")
    finally:
        cache.shutdown()


def test_request_budget_is_bounded_until_results_are_polled() -> None:
    cache = ShaderMaterialPreparationCache(max_workers=1, max_requests=1)
    try:
        first = cache.submit(_stages(), finalize=lambda prepared: prepared)
        cache.wait_workers(timeout=2.0)
        with pytest.raises(RuntimeError, match="max_requests"):
            cache.submit(
                _stages(FRAGMENT + "\n// second"),
                finalize=lambda prepared: prepared,
            )
        assert cache.poll()[0].request_id == first.request_id
    finally:
        cache.shutdown()


def test_input_validation_and_diagnostics_are_payload_free() -> None:
    with pytest.raises(ValueError, match="finite"):
        ShaderMaterialSource.capture(_stages(), material={"roughness": float("nan")})
    with pytest.raises(ValueError, match="max_source_bytes"):
        ShaderMaterialSource.capture(
            {"vertex": "x" * 32},
            max_source_bytes=8,
        )

    cache = ShaderMaterialPreparationCache(max_workers=1)
    try:
        request = cache.submit(
            _stages(),
            defines={"QUALITY": 3},
            material={"secret_payload": "not diagnostics"},
            finalize=lambda prepared: "compiled-object",
        )
        result = _finish(cache, request.request_id)
        assert result.successful
        portable = dict(cache.diagnostics().portable())
        assert all(isinstance(value, int) for value in portable.values())
        assert "payload" not in " ".join(portable)
        cache.forget(request.request_id)
        with pytest.raises(KeyError):
            cache.request(request.request_id)
    finally:
        cache.shutdown()
