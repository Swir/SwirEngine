from __future__ import annotations

from pathlib import Path

from tools.audit_runtime_lifecycle_2_0 import run_runtime_lifecycle_audit


def test_runtime_lifecycle_audit_keeps_owned_streaming_resources_bounded(tmp_path: Path) -> None:
    report = run_runtime_lifecycle_audit(
        tmp_path,
        streaming_cycles=2,
        preloader_cycles=2,
        async_requests=24,
    )

    assert report.streamed_assets == 64
    # AssetStreamingDiagnostics records its peak immediately before budget eviction, so a
    # six-resident budget can truthfully report a transient peak of seven while every settled
    # post-pump state remains within the configured limit. The harness asserts those settled states.
    assert report.streaming_peak_resident_assets <= 7
    assert report.streaming_peak_resident_bytes <= 4096
    assert report.streaming_final_resident_assets == 0
    assert report.streaming_final_resident_bytes == 0
    assert report.streaming_final_cached_paths == 0
    assert report.preloader_pending_after_shutdown == 0
    assert report.lingering_asset_threads == ()
    assert report.async_pending_after_finalize == 0
    assert report.async_cached_entries == 1


def test_runtime_lifecycle_audit_surfaces_terminal_async_request_retention(tmp_path: Path) -> None:
    report = run_runtime_lifecycle_audit(
        tmp_path,
        streaming_cycles=1,
        preloader_cycles=1,
        async_requests=12,
    )

    findings = {finding.code: finding for finding in report.findings}
    retention = findings["async_asset_terminal_records_retained"]

    assert retention.severity == "medium"
    assert report.async_retained_request_records == 12
    assert report.async_scheduler_terminal_records == 12
    assert not any(finding.severity == "high" for finding in report.findings)
