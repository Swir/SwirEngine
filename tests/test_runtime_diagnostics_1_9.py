from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from swirengine.diagnostics19 import (
    RuntimeCrashReport,
    RuntimeDiagnosticsError,
    RuntimeIdentity,
    RuntimeLogBuffer,
    SupportBundleBuilder,
    capture_exception,
    create_support_bundle,
    identity_from_project,
)
from swirengine.performance15 import PerformanceDiagnostics2
from swirengine.project19 import ProjectManifest


def _manifest(tmp_path: Path) -> ProjectManifest:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "swirproject.toml").write_text(
        '\n'.join(
            (
                'name = "Diagnostic Game"',
                'mode = "2d"',
                'entrypoint = "main.py"',
                '',
                '[content]',
                'include = []',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return ProjectManifest.load(tmp_path)


def _raise_from_project(project_root: Path) -> None:
    script = project_root / "scripts" / "fault.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    namespace: dict[str, object] = {}
    code = compile(script.read_text(encoding="utf-8"), str(script), "exec")
    exec(code, namespace, namespace)


def _report(tmp_path: Path) -> RuntimeCrashReport:
    manifest = _manifest(tmp_path)
    identity = identity_from_project(
        manifest,
        engine_version="1.9-source",
        build_id="ci-42",
        profile="windows",
    )
    logs = RuntimeLogBuffer(capacity=8)
    logs.record("info", "boot", scene="menu", token="should-not-leak")
    try:
        _raise_from_project(tmp_path)
    except RuntimeError as exc:
        return capture_exception(
            exc,
            identity=identity,
            logs=logs,
            diagnostics={"scene": "menu", "password": "also-secret"},
            project_root=tmp_path,
        )
    raise AssertionError("expected RuntimeError")


def test_log_buffer_is_bounded_and_redacts_sensitive_fields() -> None:
    logs = RuntimeLogBuffer(capacity=2)
    logs.record("info", "one", token="abc", player=1)
    logs.record("warning", "two", password="def")
    logs.record("error", "three", session_id="ghi")

    assert [item.message for item in logs.entries] == ["two", "three"]
    assert logs.entries[0].fields["password"] == "<redacted>"
    assert logs.entries[1].fields["session_id"] == "<redacted>"
    assert [item.sequence for item in logs.entries] == [1, 2]


def test_log_buffer_rejects_invalid_capacity_and_level() -> None:
    with pytest.raises(ValueError):
        RuntimeLogBuffer(capacity=0)
    logs = RuntimeLogBuffer()
    with pytest.raises(RuntimeDiagnosticsError):
        logs.record("verbose", "nope")


def test_identity_from_project_uses_only_manifest_identity(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    identity = identity_from_project(manifest, engine_version="1.9-source")
    assert identity.project_name == "Diagnostic Game"
    assert identity.project_fingerprint == manifest.fingerprint
    assert identity.engine_version == "1.9-source"


def test_capture_exception_scrubs_paths_secrets_and_source_lines(tmp_path: Path) -> None:
    report = _report(tmp_path)
    portable = report.portable()
    serialized = report.to_json()

    assert str(tmp_path) not in serialized
    assert "should-not-leak" not in serialized
    assert "also-secret" not in serialized
    assert portable["snapshot"]["diagnostics"]["password"] == "<redacted>"
    assert portable["snapshot"]["logs"][0]["fields"]["token"] == "<redacted>"
    assert portable["exception"]["trace"][-1]["filename"] == "scripts/fault.py"
    assert "source" not in portable["exception"]["trace"][-1]


def test_exception_message_redacts_inline_secret_and_project_path(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    identity = identity_from_project(manifest, engine_version="1.9-source")
    try:
        raise RuntimeError(f"failed at {tmp_path}; token=abcd")
    except RuntimeError as exc:
        report = capture_exception(exc, identity=identity, project_root=tmp_path)
    assert str(tmp_path) not in report.exception_message
    assert "abcd" not in report.exception_message
    assert "token=<redacted>" in report.exception_message


def test_performance_diagnostics_can_be_opted_into_snapshot(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    identity = identity_from_project(manifest, engine_version="1.9-source")
    performance = PerformanceDiagnostics2(history=2)
    performance.begin_frame()
    performance.set_counter("game", "entities", 12)
    performance.end_frame()
    try:
        raise ValueError("failure")
    except ValueError as exc:
        report = capture_exception(exc, identity=identity, performance=performance)
    assert report.snapshot.performance["format"] == "swirengine.performance.capture"
    frames = report.snapshot.performance["frames"]
    assert isinstance(frames, list)
    assert len(frames) == 1


def test_report_round_trip_preserves_fingerprint(tmp_path: Path) -> None:
    report = _report(tmp_path)
    path = report.export_json(tmp_path / "report.json")
    loaded = RuntimeCrashReport.load_json(path)
    assert loaded.portable() == report.portable()
    assert loaded.fingerprint == report.fingerprint


def test_report_loader_rejects_invalid_and_oversized_payloads(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    with pytest.raises(RuntimeDiagnosticsError):
        RuntimeCrashReport.load_json(invalid)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b"x" * (512 * 1024 + 1))
    with pytest.raises(RuntimeDiagnosticsError, match="exceeds"):
        RuntimeCrashReport.load_json(oversized)


def test_report_loader_rejects_wrong_schema(tmp_path: Path) -> None:
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"format": "other", "format_version": 1}), encoding="utf-8")
    with pytest.raises(RuntimeDiagnosticsError, match="format"):
        RuntimeCrashReport.load_json(path)


def test_support_bundle_contains_only_generated_safe_entries(tmp_path: Path) -> None:
    report = _report(tmp_path)
    unrelated = tmp_path / "private.txt"
    unrelated.write_text("must not be bundled", encoding="utf-8")
    result = create_support_bundle(report, tmp_path / "support.zip")

    assert result.entries == ("bundle.json", "report.json")
    with zipfile.ZipFile(result.path) as archive:
        assert tuple(sorted(archive.namelist())) == result.entries
        assert "private.txt" not in archive.namelist()
        bundle = json.loads(archive.read("bundle.json"))
        packaged = json.loads(archive.read("report.json"))
        assert bundle["privacy"]["automatic_user_file_capture"] is False
        assert bundle["privacy"]["automatic_environment_capture"] is False
        assert packaged == report.portable()
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())


def test_support_bundle_requires_zip_extension(tmp_path: Path) -> None:
    with pytest.raises(RuntimeDiagnosticsError, match=".zip"):
        SupportBundleBuilder(_report(tmp_path)).write(tmp_path / "support.dat")


def test_diagnostic_snapshot_rejects_unbounded_values(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    identity = identity_from_project(manifest, engine_version="1.9-source")
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with pytest.raises(RuntimeDiagnosticsError, match="at most 64 fields"):
            capture_exception(
                exc,
                identity=identity,
                diagnostics={f"key-{index}": index for index in range(65)},
            )


def test_non_finite_diagnostics_are_rejected(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    identity = identity_from_project(manifest, engine_version="1.9-source")
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with pytest.raises(RuntimeDiagnosticsError, match="finite"):
            capture_exception(exc, identity=identity, diagnostics={"fps": float("nan")})


def test_bundle_report_hash_matches_packaged_bytes(tmp_path: Path) -> None:
    report = _report(tmp_path)
    result = create_support_bundle(report, tmp_path / "support.zip")
    with zipfile.ZipFile(result.path) as archive:
        manifest = json.loads(archive.read("bundle.json"))
    assert manifest["report_fingerprint"] == report.fingerprint
    assert manifest["report_sha256"] == result.report_sha256
