from __future__ import annotations

import hashlib
import json
import traceback
from itertools import count
from pathlib import Path

import pytest

from swirengine.editor_multiplayer_debugger22 import (
    DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22,
    EditorMultiplayerDebugger22,
    EditorMultiplayerDebuggerError22,
)
from swirengine.multiplayer20 import MultiplayerCompatibility, ProductionMultiplayerSession
from swirengine.multiplayer_debugger22 import (
    MultiplayerDebugger22,
    MultiplayerDebuggerError22,
)
from swirengine.network_latency22 import NetworkRoundTripProbe22


def _compatibility() -> MultiplayerCompatibility:
    return MultiplayerCompatibility(
        project_id="private-project",
        protocol_version="2.2",
        build_id="private-build",
        replication_schema="private-schema",
        content_fingerprint="private-content",
    )


def _session(*, clients: int = 1) -> ProductionMultiplayerSession:
    tokens = count()
    session = ProductionMultiplayerSession(
        "private-session",
        "private-host-id",
        _compatibility(),
        max_members=clients,
        token_factory=lambda: f"private-token-{next(tokens):04d}",
    )
    for index in range(1, clients):
        session.join(f"private-client-{index}", _compatibility())
    return session


def test_transient_controller_attaches_real_session_and_samples_privately(tmp_path: Path) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    session = _session(clients=2)

    initial = controller.attach_session(session)
    sampled = controller.sample(
        "private-host-id",
        1,
        sent_bytes=120,
        received_bytes=80,
        replicated_entities=3,
        entity_budget=6,
    )

    assert controller.attached is True
    assert controller.closed is False
    assert controller.dirty is False
    assert initial["kind"] == "snapshot"
    assert sampled == controller.snapshot()
    assert sampled["peers"][0]["alias"] == "peer-000"
    assert sampled["peers"][0]["samples"][0]["counters"]["traffic.sent_bytes"] == 120
    encoded = controller.capture_json()
    assert "private-host-id" not in encoded
    assert "private-session" not in encoded
    assert "private-token" not in encoded
    assert controller.fingerprint() == hashlib.sha256(controller.capture_bytes()).hexdigest()
    assert not hasattr(controller, "save")


def test_session_detach_drops_all_transient_samples_and_probe_references(tmp_path: Path) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    first = _session()
    probe = NetworkRoundTripProbe22(nonce_factory=lambda: "private-nonce-00000001")
    controller.attach(first)
    controller.sample("private-host-id", 1)
    controller.attach_round_trip_probe("private-host-id", probe)

    assert controller.detach_session() is True
    assert controller.attached is False
    assert controller.detach_session() is False
    with pytest.raises(EditorMultiplayerDebuggerError22) as detached:
        controller.snapshot()
    assert detached.value.code == "session_not_attached"

    controller.attach(_session())
    reopened = controller.snapshot()
    assert reopened["peers"][0]["samples"] == []
    assert "round_trip" not in reopened["peers"][0]


def test_real_round_trip_probe_can_be_attached_and_detached(tmp_path: Path) -> None:
    clock = [10.0]
    probe = NetworkRoundTripProbe22(
        clock=lambda: clock[0],
        nonce_factory=lambda: "private-nonce-00000001",
    )
    ping = probe.create_ping()
    clock[0] += 0.018
    probe.accept_pong(probe.reply_to_ping(ping))
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())

    attached = controller.attach_round_trip_probe("private-host-id", probe)
    assert attached["peers"][0]["round_trip"]["latest_ms"] == pytest.approx(18.0)
    assert "private-nonce" not in controller.capture_json()
    assert controller.detach_round_trip_probe("private-host-id") is True
    assert controller.detach_round_trip_probe("private-host-id") is False
    assert "round_trip" not in controller.snapshot()["peers"][0]


def test_capture_export_is_deterministic_ascii_atomic_and_confined(tmp_path: Path) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())
    controller.sample("private-host-id", 1, sent_bytes=9)
    expected = controller.capture_bytes()

    target = controller.export_capture()
    first = target.read_bytes()
    second_target = controller.export_capture(DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22)

    assert target == (tmp_path / DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22).resolve()
    assert second_target == target
    assert first == expected == target.read_bytes()
    first.decode("ascii")
    assert json.loads(first)["kind"] == "capture"
    assert list(target.parent.glob("*.tmp")) == []
    assert list(target.parent.glob(".*.tmp")) == []


@pytest.mark.parametrize(
    "path",
    [
        "capture.json",
        ".swir",
        ".swir/capture.txt",
        ".swir/../capture.json",
        "../.swir/capture.json",
        "/tmp/capture.json",
        "C:\\temp\\capture.json",
        ".swir/bad:name.json",
        ".swir//capture.json",
        ".swir/./capture.json",
        ".swir/CON.json",
    ],
)
def test_capture_export_rejects_nonportable_or_unconfined_paths(
    tmp_path: Path,
    path: str,
) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())

    with pytest.raises(EditorMultiplayerDebuggerError22) as rejected:
        controller.export_capture(path)

    assert rejected.value.code == "invalid_capture_path"
    assert not (tmp_path.parent / "capture.json").exists()


def test_capture_export_rejects_directory_and_symlink_targets_without_replacement(
    tmp_path: Path,
) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())
    capture_root = tmp_path / ".swir" / "multiplayer-debugger"
    capture_root.mkdir(parents=True)
    directory_target = capture_root / "directory.json"
    directory_target.mkdir()

    with pytest.raises(EditorMultiplayerDebuggerError22) as directory:
        controller.export_capture(".swir/multiplayer-debugger/directory.json")
    assert directory.value.code == "unsafe_capture_path"
    assert directory_target.is_dir()

    outside = tmp_path.parent / f"{tmp_path.name}-outside-capture.json"
    outside.write_text("sentinel", encoding="ascii")
    link = capture_root / "linked.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this runner")
    try:
        with pytest.raises(EditorMultiplayerDebuggerError22) as linked:
            controller.export_capture(".swir/multiplayer-debugger/linked.json")
        assert linked.value.code == "unsafe_capture_path"
        assert outside.read_text(encoding="ascii") == "sentinel"
    finally:
        link.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)


def test_capture_export_rejects_symlinked_swir_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-directory"
    outside.mkdir()
    swir = tmp_path / ".swir"
    try:
        swir.symlink_to(outside, target_is_directory=True)
    except OSError:
        outside.rmdir()
        pytest.skip("directory symlinks are unavailable on this runner")
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())
    try:
        with pytest.raises(EditorMultiplayerDebuggerError22) as rejected:
            controller.export_capture()
        assert rejected.value.code == "unsafe_capture_path"
        assert list(outside.iterdir()) == []
    finally:
        swir.unlink(missing_ok=True)
        outside.rmdir()


def test_capture_export_rejects_project_root_replaced_by_symlink(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    moved_project = tmp_path / "moved-project"
    outside = tmp_path / "outside"
    outside.mkdir()
    controller = EditorMultiplayerDebugger22(project)
    controller.attach(_session())
    project.rename(moved_project)
    try:
        project.symlink_to(outside, target_is_directory=True)
    except OSError:
        moved_project.rename(project)
        pytest.skip("directory symlinks are unavailable on this runner")
    try:
        with pytest.raises(EditorMultiplayerDebuggerError22) as rejected:
            controller.export_capture()
        assert rejected.value.code == "unsafe_capture_path"
        assert list(outside.iterdir()) == []
    finally:
        project.unlink(missing_ok=True)


def test_hard_byte_limit_is_checked_before_existing_capture_is_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())
    target = tmp_path / DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22
    target.parent.mkdir(parents=True)
    target.write_bytes(b"sentinel")
    oversized = b"x" * (2 * 1024 * 1024 + 1)
    monkeypatch.setattr(MultiplayerDebugger22, "capture_bytes", lambda _self: oversized)

    with pytest.raises(EditorMultiplayerDebuggerError22) as rejected:
        controller.export_capture()

    assert rejected.value.code == "capture_too_large"
    assert target.read_bytes() == b"sentinel"
    assert list(target.parent.glob("*.tmp")) == []


def test_invalid_capture_payload_has_no_hidden_decoder_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())
    secret = "private invalid capture payload"
    monkeypatch.setattr(
        MultiplayerDebugger22,
        "capture_bytes",
        lambda _self: f'{{"secret":"{secret}"'.encode("ascii"),
    )

    with pytest.raises(EditorMultiplayerDebuggerError22) as invalid:
        controller.capture_bytes()

    assert invalid.value.code == "invalid_capture"
    assert invalid.value.__cause__ is None
    assert invalid.value.__context__ is None
    assert secret not in repr(invalid.value)


def test_atomic_write_failure_preserves_existing_capture_and_sanitizes_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())
    target = tmp_path / DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22
    target.parent.mkdir(parents=True)
    target.write_bytes(b"sentinel")

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("private-filesystem-path-and-error")

    monkeypatch.setattr("swirengine.editor_multiplayer_debugger22.os.replace", fail_replace)
    with pytest.raises(EditorMultiplayerDebuggerError22) as failed:
        controller.export_capture()

    assert failed.value.code == "capture_write_failed"
    assert failed.value.__cause__ is None
    assert failed.value.__context__ is None
    assert "private-filesystem" not in str(failed.value)
    assert target.read_bytes() == b"sentinel"
    assert list(target.parent.glob("*.tmp")) == []


def test_runtime_provider_errors_are_sanitized_and_do_not_write_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())

    def fail_sample(_self: object, *_args: object, **_kwargs: object) -> None:
        raise MultiplayerDebuggerError22(
            "private-provider-code",
            "private-provider-error-and-identifier",
        )

    monkeypatch.setattr(MultiplayerDebugger22, "sample_peer", fail_sample)

    with pytest.raises(EditorMultiplayerDebuggerError22) as failed:
        controller.sample("private-host-id", 1)

    assert failed.value.code == "sample_failed"
    assert "private-provider" not in str(failed.value)
    assert failed.value.__cause__ is None
    assert failed.value.__context__ is None
    rendered = "".join(
        traceback.format_exception(
            type(failed.value), failed.value, failed.value.__traceback__
        )
    )
    assert "private-provider-error-and-identifier" not in rendered
    assert not (tmp_path / ".swir").exists()


def test_close_is_idempotent_and_releases_transient_debugger(tmp_path: Path) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    controller.attach(_session())

    controller.close()
    controller.close()

    assert controller.closed is True
    assert controller.attached is False
    assert controller.dirty is False
    with pytest.raises(EditorMultiplayerDebuggerError22) as closed:
        controller.attach(_session())
    assert closed.value.code == "debugger_closed"
