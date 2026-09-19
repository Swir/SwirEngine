from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.assets import AssetManager
from swirengine.assets17 import AsyncAssetPipeline, AsyncAssetState
from swirengine.jobs17 import JobSchedulerError


def _write(root: Path, name: str, value: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _pipeline(root: Path) -> AsyncAssetPipeline:
    pipeline = AsyncAssetPipeline(AssetManager(root), max_workers=2, max_pending=32)
    pipeline.register_processor(
        "data",
        suffixes=[".dat"],
        decode=lambda path, _context: path.read_text(encoding="utf-8"),
    )
    return pipeline


def _finish(pipeline: AsyncAssetPipeline, request_id: int):
    pipeline.wait_workers(timeout=2.0)
    while request_id in pipeline.pending_request_ids():
        pipeline.poll(max_items=32)
    return pipeline.result(request_id)


def test_forget_reclaims_finalized_pipeline_and_scheduler_records(tmp_path: Path) -> None:
    source = _write(tmp_path, "asset.dat", "payload")
    pipeline = _pipeline(tmp_path)
    try:
        request = pipeline.submit(source)
        result = _finish(pipeline, request.request_id)

        forgotten = pipeline.forget(request.request_id)

        assert forgotten == result
        with pytest.raises(KeyError):
            pipeline.request(request.request_id)
        with pytest.raises(KeyError):
            pipeline._scheduler.state(request.job_id)
        assert pipeline.pending_request_ids() == ()
        assert pipeline._scheduler.diagnostics().succeeded == 0
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)


def test_forget_refuses_unfinished_request(tmp_path: Path) -> None:
    source = _write(tmp_path, "asset.dat", "payload")
    pipeline = _pipeline(tmp_path)
    try:
        request = pipeline.submit(source)
        with pytest.raises(JobSchedulerError, match="not finalized"):
            pipeline.forget(request.request_id)
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)


def test_forget_preserves_dependency_references_until_dependents_are_reclaimed(
    tmp_path: Path,
) -> None:
    first_path = _write(tmp_path, "first.dat", "first")
    second_path = _write(tmp_path, "second.dat", "second")
    pipeline = _pipeline(tmp_path)
    try:
        first = pipeline.submit(first_path)
        second = pipeline.submit(second_path, depends_on=[first.request_id])
        pipeline.wait_workers(timeout=2.0)
        pipeline.poll(max_items=32)

        with pytest.raises(JobSchedulerError, match="retained dependents"):
            pipeline.forget(first.request_id)

        assert pipeline.forget(second.request_id).successful
        assert pipeline.forget(first.request_id).successful
        assert pipeline._records == {}
        assert pipeline._scheduler.diagnostics().succeeded == 0
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)


def test_prune_finalized_reclaims_dependency_graph_leaves_first(tmp_path: Path) -> None:
    for name in ("a.dat", "b.dat", "c.dat"):
        _write(tmp_path, name, name)
    pipeline = _pipeline(tmp_path)
    try:
        first = pipeline.submit("a.dat")
        second = pipeline.submit("b.dat", depends_on=[first.request_id])
        third = pipeline.submit("c.dat", depends_on=[second.request_id])
        pipeline.wait_workers(timeout=2.0)
        pipeline.poll(max_items=32)

        assert pipeline.prune_finalized(max_items=2) == (third.request_id, second.request_id)
        assert pipeline.request(first.request_id) == first
        assert pipeline.prune_finalized() == (first.request_id,)
        assert pipeline._records == {}
        scheduler = pipeline._scheduler.diagnostics()
        assert scheduler.succeeded == 0
        assert scheduler.failed == 0
        assert scheduler.cancelled == 0
        assert scheduler.blocked == 0
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)


def test_prune_finalized_covers_failed_and_cancelled_requests(tmp_path: Path) -> None:
    _write(tmp_path, "good.dat", "good")
    _write(tmp_path, "bad.fail", "bad")
    _write(tmp_path, "cancel.dat", "cancel")
    pipeline = _pipeline(tmp_path)
    pipeline.register_processor(
        "fail",
        suffixes=[".fail"],
        decode=lambda _path, _context: (_ for _ in ()).throw(RuntimeError("decode failed")),
    )
    try:
        good = pipeline.submit("good.dat")
        failed = pipeline.submit("bad.fail")
        cancelled = pipeline.submit("cancel.dat")
        pipeline.wait_workers(timeout=2.0)
        assert pipeline.cancel(cancelled.request_id)
        pipeline.poll(max_items=32)

        assert pipeline.result(good.request_id).state is AsyncAssetState.COMPLETED
        assert pipeline.result(failed.request_id).state is AsyncAssetState.FAILED
        assert pipeline.result(cancelled.request_id).state is AsyncAssetState.CANCELLED
        assert pipeline.prune_finalized() == (
            cancelled.request_id,
            failed.request_id,
            good.request_id,
        )
        assert pipeline._records == {}
        scheduler = pipeline._scheduler.diagnostics()
        assert scheduler.succeeded == 0
        assert scheduler.failed == 0
        assert scheduler.cancelled == 0
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)


def test_repeated_finalize_and_forget_keeps_request_bookkeeping_bounded(tmp_path: Path) -> None:
    source = _write(tmp_path, "repeat.dat", "stable")
    pipeline = _pipeline(tmp_path)
    try:
        for _ in range(128):
            request = pipeline.submit(source)
            result = _finish(pipeline, request.request_id)
            assert result.successful
            assert pipeline.forget(request.request_id) == result
            assert len(pipeline._records) == 0
            scheduler = pipeline._scheduler.diagnostics()
            assert scheduler.succeeded == 0
            assert scheduler.failed == 0
            assert scheduler.cancelled == 0
            assert scheduler.blocked == 0

        diagnostics = pipeline.diagnostics()
        assert diagnostics.submitted_total == 128
        assert diagnostics.completed_total == 128
        assert diagnostics.pending == 0
        assert diagnostics.cached_entries == 1
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)


def test_prune_finalized_validates_budget(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path)
    try:
        for value in (0, -1, True):
            with pytest.raises(ValueError, match="positive integer or None"):
                pipeline.prune_finalized(max_items=value)
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)
