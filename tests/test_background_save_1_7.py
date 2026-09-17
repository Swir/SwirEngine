from __future__ import annotations

import threading

import pytest

from swirengine.background_save17 import (
    BackgroundSavePipeline,
    BackgroundSaveState,
    PreparedSaveSnapshot,
)
from swirengine.storage15 import ProfileSaveManager2, SaveSlotStore2


class GateStore(SaveSlotStore2):
    def __init__(self, path, started: threading.Event, release: threading.Event) -> None:
        super().__init__(path)
        self.started = started
        self.release = release

    def save(self, data, *, metadata=None):
        self.started.set()
        assert self.release.wait(5.0)
        return super().save(data, metadata=metadata)


class FailingStore(SaveSlotStore2):
    def save(self, data, *, metadata=None):
        raise OSError("disk unavailable")


def test_snapshot_is_captured_on_owner_thread_and_detached_from_live_state(tmp_path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    owner_thread = threading.get_ident()
    live = {"player": {"hp": 100}, "inventory": ["key"]}
    capture_threads: list[int] = []

    def snapshot():
        capture_threads.append(threading.get_ident())
        return live

    with BackgroundSavePipeline(max_workers=1) as pipeline:
        pipeline.submit("manual", store, snapshot, metadata={"reason": "checkpoint"})
        live["player"]["hp"] = 1
        live["inventory"].append("late-mutation")
        outcome = pipeline.run_until_idle()[0]

    loaded = store.load()
    assert capture_threads == [owner_thread]
    assert outcome.state is BackgroundSaveState.SUCCEEDED
    assert loaded.data["player"] == {"hp": 100}
    assert loaded.data["inventory"] == ["key"]
    assert loaded.metadata == {"reason": "checkpoint"}


def test_successful_background_save_is_verified_and_reports_revision(tmp_path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")

    with BackgroundSavePipeline(max_workers=2) as pipeline:
        sequence = pipeline.submit("save-1", store, {"score": 42})
        outcome = pipeline.run_until_idle()[0]
        diagnostics = pipeline.diagnostics()

    assert sequence == 1
    assert outcome.successful
    assert outcome.receipt is not None
    assert outcome.receipt.revision == 1
    assert outcome.receipt.path == store.path
    assert outcome.receipt.snapshot_bytes > 0
    assert diagnostics.verified_writes_total == 1
    assert diagnostics.unfinished == 0


def test_second_write_preserves_save_profile_2_backup_recovery_semantics(tmp_path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")

    with BackgroundSavePipeline(max_workers=1) as pipeline:
        pipeline.submit("first", store, {"checkpoint": 1})
        first = pipeline.run_until_idle()[0]
        pipeline.submit("second", store, {"checkpoint": 2})
        second = pipeline.run_until_idle()[0]

    assert first.receipt is not None and first.receipt.revision == 1
    assert second.receipt is not None and second.receipt.revision == 2
    assert store.backup_path.exists()

    store.path.write_text("{corrupt", encoding="utf-8")
    recovered = store.load()
    assert recovered.recovered
    assert recovered.revision == 1
    assert recovered.data["checkpoint"] == 1


@pytest.mark.parametrize(
    "payload,error_type",
    [
        ({"bad": float("nan")}, ValueError),
        ({1: "bad-key"}, TypeError),
        ({"bad": object()}, TypeError),
    ],
)
def test_invalid_snapshot_is_rejected_before_job_or_file_creation(
    tmp_path, payload, error_type
) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    pipeline = BackgroundSavePipeline(max_workers=1)
    try:
        with pytest.raises(error_type):
            pipeline.submit("invalid", store, payload)
        assert not store.path.exists()
        assert pipeline.diagnostics().submitted_total == 0
    finally:
        pipeline.shutdown()


def test_duplicate_request_id_is_rejected(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    first = GateStore(tmp_path / "first.json", started, release)
    second = SaveSlotStore2(tmp_path / "second.json")

    with BackgroundSavePipeline(max_workers=1) as pipeline:
        pipeline.submit("same-id", first, {"value": 1})
        assert started.wait(5.0)
        with pytest.raises(ValueError, match="already exists"):
            pipeline.submit("same-id", second, {"value": 2})
        release.set()
        assert pipeline.run_until_idle()[0].successful


def test_same_slot_is_exclusive_while_write_is_unfinished(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    store = GateStore(tmp_path / "slot.json", started, release)

    with BackgroundSavePipeline(max_workers=2) as pipeline:
        pipeline.submit("first", store, {"value": 1})
        assert started.wait(5.0)
        with pytest.raises(RuntimeError, match="slot is busy"):
            pipeline.submit("second", store, {"value": 2})
        release.set()
        assert pipeline.run_until_idle()[0].successful


def test_queued_cancellation_never_creates_target_file(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    blocker = GateStore(tmp_path / "blocker.json", started, release)
    target = SaveSlotStore2(tmp_path / "cancelled.json")

    with BackgroundSavePipeline(max_workers=1) as pipeline:
        pipeline.submit("blocker", blocker, {"value": 1})
        assert started.wait(5.0)
        pipeline.submit("cancelled", target, {"value": 2})
        assert pipeline.cancel("cancelled") is True
        release.set()
        outcomes = pipeline.run_until_idle()

    by_id = {outcome.request_id: outcome for outcome in outcomes}
    assert by_id["blocker"].successful
    assert by_id["cancelled"].state is BackgroundSaveState.CANCELLED
    assert not target.path.exists()


def test_cancellation_is_refused_after_atomic_commit_boundary_starts(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    store = GateStore(tmp_path / "slot.json", started, release)

    with BackgroundSavePipeline(max_workers=1) as pipeline:
        pipeline.submit("committing", store, {"value": 7})
        assert started.wait(5.0)
        assert pipeline.state("committing") is BackgroundSaveState.COMMITTING
        assert pipeline.cancel("committing") is False
        release.set()
        outcome = pipeline.run_until_idle()[0]
        diagnostics = pipeline.diagnostics()

    assert outcome.successful
    assert store.load().data["value"] == 7
    assert diagnostics.cancellation_refused_total == 1


def test_failed_write_is_isolated_from_other_slots(tmp_path) -> None:
    broken = FailingStore(tmp_path / "broken.json")
    healthy = SaveSlotStore2(tmp_path / "healthy.json")

    with BackgroundSavePipeline(max_workers=2) as pipeline:
        pipeline.submit("broken", broken, {"value": 1})
        pipeline.submit("healthy", healthy, {"value": 2})
        outcomes = pipeline.run_until_idle()

    by_id = {outcome.request_id: outcome for outcome in outcomes}
    assert by_id["broken"].state is BackgroundSaveState.FAILED
    assert by_id["broken"].error_type == "OSError"
    assert by_id["healthy"].successful
    assert healthy.load().data["value"] == 2


def test_profile_manager_convenience_uses_additive_saves_v2_layout(tmp_path) -> None:
    manager = ProfileSaveManager2(tmp_path, "hero")

    with BackgroundSavePipeline(max_workers=1) as pipeline:
        pipeline.submit_profile(
            "profile-checkpoint",
            manager,
            "campaign",
            {"chapter": 4},
            metadata={"kind": "manual"},
        )
        outcome = pipeline.run_until_idle()[0]

    assert outcome.successful
    assert manager.slot_path("campaign").exists()
    assert "saves-v2" in manager.slot_path("campaign").parts
    assert manager.load("campaign").data["chapter"] == 4


def test_snapshot_fingerprint_is_canonical_across_mapping_order(tmp_path) -> None:
    first = SaveSlotStore2(tmp_path / "first.json")
    second = SaveSlotStore2(tmp_path / "second.json")

    with BackgroundSavePipeline(max_workers=2) as pipeline:
        pipeline.submit("first", first, {"a": 1, "b": [2, 3]}, metadata={"x": True})
        pipeline.submit("second", second, {"b": [2, 3], "a": 1}, metadata={"x": True})
        outcomes = pipeline.run_until_idle()

    fingerprints = {
        outcome.receipt.snapshot_fingerprint
        for outcome in outcomes
        if outcome.receipt is not None
    }
    assert len(fingerprints) == 1


def test_prepared_snapshot_detects_manual_tampering() -> None:
    prepared = PreparedSaveSnapshot.capture("save", {"value": 1})
    tampered = PreparedSaveSnapshot(
        request_id=prepared.request_id,
        data_json='{"value":2}',
        metadata_json=prepared.metadata_json,
        fingerprint=prepared.fingerprint,
        captured_thread_id=prepared.captured_thread_id,
    )
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        tampered.decode()


def test_owner_thread_operations_reject_cross_thread_submission(tmp_path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json")
    pipeline = BackgroundSavePipeline(max_workers=1)
    errors: list[RuntimeError] = []

    def submit_elsewhere() -> None:
        try:
            pipeline.submit("wrong-thread", store, {"value": 1})
        except RuntimeError as exc:
            errors.append(exc)

    worker = threading.Thread(target=submit_elsewhere)
    worker.start()
    worker.join(timeout=5.0)
    try:
        assert len(errors) == 1
        assert "owner-thread" in str(errors[0])
        assert not store.path.exists()
    finally:
        pipeline.shutdown()


def test_store_defaults_are_compatible_with_subset_verification(tmp_path) -> None:
    store = SaveSlotStore2(tmp_path / "slot.json", defaults={"difficulty": "normal"})

    with BackgroundSavePipeline(max_workers=1) as pipeline:
        pipeline.submit("defaults", store, {"score": 5})
        outcome = pipeline.run_until_idle()[0]

    assert outcome.successful
    assert store.load().data == {"difficulty": "normal", "score": 5}
