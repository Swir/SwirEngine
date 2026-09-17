from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from swirengine.assets import AssetManager
from swirengine.assets17 import AsyncAssetPipeline, AsyncAssetState
from swirengine.jobs17 import JobRejectedError


@pytest.fixture
def pipeline_factory() -> Callable[..., AsyncAssetPipeline]:
    pipelines: list[AsyncAssetPipeline] = []

    def create(root: Path, **kwargs: int) -> AsyncAssetPipeline:
        pipeline = AsyncAssetPipeline(AssetManager(root), **kwargs)
        pipelines.append(pipeline)
        return pipeline

    yield create

    for pipeline in pipelines:
        pipeline.shutdown(wait=True, cancel_pending=True)


def _write(root: Path, name: str, value: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _finish(pipeline: AsyncAssetPipeline, request_id: int):
    pipeline.wait_workers(timeout=2.0)
    while request_id in pipeline.pending_request_ids():
        pipeline.poll(max_items=1)
    return pipeline.result(request_id)


def test_decode_runs_in_worker_and_finalizer_only_runs_during_poll(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "texture.dat", "hello")
    pipeline = pipeline_factory(tmp_path, max_workers=2, max_pending=8)
    main_thread = threading.get_ident()
    calls: dict[str, int] = {}

    def decode(path: Path, _context) -> str:
        calls["decode"] = threading.get_ident()
        return path.read_text(encoding="utf-8").upper()

    def finalize(value: str) -> str:
        calls["finalize"] = threading.get_ident()
        return f"gpu:{value}"

    pipeline.register_processor("data", suffixes=[".dat"], decode=decode, finalizer=finalize)
    pipeline.submit("texture.dat")
    pipeline.wait_workers(timeout=2.0)

    assert "finalize" not in calls
    assert calls["decode"] != main_thread
    results = pipeline.poll(max_items=1)
    assert results[0].value == "gpu:HELLO"
    assert calls["finalize"] == main_thread


def test_cook_stage_receives_decoded_value(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "mesh.raw", "2,3,5")
    pipeline = pipeline_factory(tmp_path)
    pipeline.register_processor(
        "mesh",
        suffixes=["raw"],
        decode=lambda path, _ctx: [int(item) for item in path.read_text().split(",")],
        cook=lambda values, _ctx: sum(values),
    )

    result = _finish(pipeline, pipeline.submit("mesh.raw").request_id)
    assert result.successful
    assert result.value == 10


def test_request_dependencies_gate_work_and_expose_background_products(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "a.dep", "7")
    _write(tmp_path, "b.dep", "5")
    pipeline = pipeline_factory(tmp_path, max_workers=2)

    def decode(path: Path, context) -> int:
        own = int(path.read_text())
        return own + sum(context.dependency_values.values())

    pipeline.register_processor("dep", suffixes=[".dep"], decode=decode)
    first = pipeline.submit("a.dep")
    second = pipeline.submit("b.dep", depends_on=[first.request_id])

    pipeline.wait_workers(timeout=2.0)
    pipeline.poll(max_items=8)
    assert pipeline.result(first.request_id).value == 7
    assert pipeline.result(second.request_id).value == 12


def test_file_dependency_change_invalidates_worker_cache(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    source = _write(tmp_path, "material.mat", "body")
    include = _write(tmp_path, "common.inc", "A")
    pipeline = pipeline_factory(tmp_path)
    calls = 0

    def decode(path: Path, context) -> str:
        nonlocal calls
        calls += 1
        return path.read_text() + context.file_dependencies[0].read_text()

    pipeline.register_processor(
        "material",
        suffixes=[".mat"],
        decode=decode,
        dependencies=lambda _path: [include],
    )

    first = _finish(pipeline, pipeline.submit(source).request_id)
    second = _finish(pipeline, pipeline.submit(source).request_id)
    include.write_text("B", encoding="utf-8")
    third = _finish(pipeline, pipeline.submit(source).request_id)

    assert not first.cache_hit
    assert second.cache_hit
    assert not third.cache_hit
    assert third.value == "bodyB"
    assert calls == 2


def test_poll_enforces_explicit_finalize_budget(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    for index in range(3):
        _write(tmp_path, f"{index}.x", str(index))
    pipeline = pipeline_factory(tmp_path, max_workers=3)
    finalized: list[str] = []
    pipeline.register_processor(
        "x",
        suffixes=[".x"],
        decode=lambda path, _ctx: path.name,
        finalizer=lambda value: finalized.append(value) or value,
    )
    requests = [pipeline.submit(f"{index}.x") for index in range(3)]
    pipeline.wait_workers(timeout=2.0)

    assert len(pipeline.poll(max_items=1)) == 1
    assert len(finalized) == 1
    assert len(pipeline.pending_request_ids()) == 2
    pipeline.poll(max_items=1)
    assert len(finalized) == 2
    pipeline.poll(max_items=1)
    assert all(pipeline.result(item.request_id).successful for item in requests)


def test_finalizer_failure_is_isolated_from_other_assets(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "bad.bin", "bad")
    _write(tmp_path, "good.bin", "good")
    pipeline = pipeline_factory(tmp_path)

    def finalize(value: str) -> str:
        if value == "bad":
            raise RuntimeError("upload failed")
        return value

    pipeline.register_processor(
        "binary",
        suffixes=[".bin"],
        decode=lambda path, _ctx: path.read_text(),
        finalizer=finalize,
    )
    bad = pipeline.submit("bad.bin")
    good = pipeline.submit("good.bin")
    pipeline.wait_workers(timeout=2.0)
    pipeline.poll(max_items=8)

    assert pipeline.result(bad.request_id).state is AsyncAssetState.FAILED
    assert pipeline.result(bad.request_id).error_type == "RuntimeError"
    assert pipeline.result(good.request_id).successful


def test_cancellation_after_worker_completion_discards_finalizer(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "sound.snd", "pcm")
    pipeline = pipeline_factory(tmp_path)
    finalized = 0

    def finalize(value: str) -> str:
        nonlocal finalized
        finalized += 1
        return value

    pipeline.register_processor(
        "sound",
        suffixes=[".snd"],
        decode=lambda path, _ctx: path.read_text(),
        finalizer=finalize,
    )
    request = pipeline.submit("sound.snd")
    pipeline.wait_workers(timeout=2.0)

    assert pipeline.cancel(request.request_id)
    result = pipeline.poll(max_items=1)[0]
    assert result.state is AsyncAssetState.CANCELLED
    assert finalized == 0
    assert pipeline.diagnostics().cached_entries == 0


def test_worker_exception_is_reported_without_raising_from_poll(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "broken.bad", "x")
    pipeline = pipeline_factory(tmp_path)

    def decode(_path: Path, _ctx) -> str:
        raise ValueError("decode failed")

    pipeline.register_processor("broken", suffixes=[".bad"], decode=decode)
    request = pipeline.submit("broken.bad")
    result = _finish(pipeline, request.request_id)

    assert result.state is AsyncAssetState.FAILED
    assert result.error_type == "ValueError"
    assert "decode failed" in (result.error_message or "")


def test_source_changed_during_decode_is_refused_as_stale(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    source = _write(tmp_path, "moving.txt", "before")
    pipeline = pipeline_factory(tmp_path)

    def decode(path: Path, _ctx) -> str:
        value = path.read_text()
        path.write_text("after-change", encoding="utf-8")
        return value

    pipeline.register_processor("text", suffixes=[".txt"], decode=decode)
    result = _finish(pipeline, pipeline.submit(source).request_id)

    assert result.state is AsyncAssetState.STALE
    assert pipeline.diagnostics().cached_entries == 0


def test_stale_result_does_not_poison_next_build_cache(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    source = _write(tmp_path, "retry.retry", "first")
    pipeline = pipeline_factory(tmp_path)
    mutate = True
    calls = 0

    def decode(path: Path, _ctx) -> str:
        nonlocal calls, mutate
        calls += 1
        value = path.read_text()
        if mutate:
            mutate = False
            path.write_text("second-value", encoding="utf-8")
        return value

    pipeline.register_processor("retry", suffixes=[".retry"], decode=decode)
    first = _finish(pipeline, pipeline.submit(source).request_id)
    second = _finish(pipeline, pipeline.submit(source).request_id)

    assert first.state is AsyncAssetState.STALE
    assert second.successful
    assert second.value == "second-value"
    assert not second.cache_hit
    assert calls == 2


def test_scheduler_backpressure_is_preserved_atomically(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    for name in ("a.lock", "b.lock", "c.lock"):
        _write(tmp_path, name, name)
    gate = threading.Event()
    pipeline = pipeline_factory(tmp_path, max_workers=1, max_pending=2)

    def decode(path: Path, context) -> str:
        while not gate.wait(0.01):
            context.raise_if_cancelled()
        return path.name

    pipeline.register_processor("lock", suffixes=[".lock"], decode=decode)
    first = pipeline.submit("a.lock")
    second = pipeline.submit("b.lock")
    with pytest.raises(JobRejectedError, match="max_pending"):
        pipeline.submit("c.lock")

    gate.set()
    pipeline.wait_workers(timeout=2.0)
    pipeline.poll(max_items=8)
    assert pipeline.result(first.request_id).successful
    assert pipeline.result(second.request_id).successful
    assert pipeline.diagnostics().submitted_total == 2


def test_processor_suffix_collisions_are_rejected(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    pipeline = pipeline_factory(tmp_path)
    pipeline.register_processor("one", suffixes=[".png"], decode=lambda _path, _ctx: None)

    with pytest.raises(ValueError, match="already registered"):
        pipeline.register_processor("two", suffixes=["png"], decode=lambda _path, _ctx: None)


def test_invalid_request_dependencies_are_rejected_before_scheduler_submit(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "asset.a", "x")
    pipeline = pipeline_factory(tmp_path)
    pipeline.register_processor("a", suffixes=[".a"], decode=lambda _path, _ctx: 1)

    with pytest.raises(KeyError):
        pipeline.submit("asset.a", depends_on=[99])
    with pytest.raises(ValueError, match="positive integers"):
        pipeline.submit("asset.a", depends_on=[True])

    assert pipeline.diagnostics().submitted_total == 0


def test_diagnostics_account_for_cache_hits_misses_and_failures(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "good.ok", "value")
    _write(tmp_path, "bad.fail", "value")
    pipeline = pipeline_factory(tmp_path)
    pipeline.register_processor("ok", suffixes=[".ok"], decode=lambda path, _ctx: path.read_text())
    pipeline.register_processor(
        "fail",
        suffixes=[".fail"],
        decode=lambda _path, _ctx: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    _finish(pipeline, pipeline.submit("good.ok").request_id)
    cached = _finish(pipeline, pipeline.submit("good.ok").request_id)
    failed = _finish(pipeline, pipeline.submit("bad.fail").request_id)
    diagnostics = pipeline.diagnostics()

    assert cached.cache_hit
    assert failed.state is AsyncAssetState.FAILED
    assert diagnostics.submitted_total == 3
    assert diagnostics.completed_total == 2
    assert diagnostics.failed_total == 1
    assert diagnostics.cache_misses_total == 1
    assert diagnostics.cache_hits_total == 1
    assert diagnostics.pending == 0


def test_cache_invalidation_is_scoped_by_processor_and_path(
    tmp_path: Path,
    pipeline_factory: Callable[..., AsyncAssetPipeline],
) -> None:
    _write(tmp_path, "asset.x", "value")
    pipeline = pipeline_factory(tmp_path)
    pipeline.register_processor("x", suffixes=[".x"], decode=lambda path, _ctx: path.read_text())
    _finish(pipeline, pipeline.submit("asset.x").request_id)

    assert pipeline.diagnostics().cached_entries == 1
    assert pipeline.invalidate("asset.x", processor="other") == 0
    assert pipeline.invalidate("asset.x", processor="x") == 1
    assert pipeline.diagnostics().cached_entries == 0
