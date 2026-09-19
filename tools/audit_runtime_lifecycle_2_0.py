from __future__ import annotations

import argparse
import json
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from swirengine.asset_pipeline import AssetPreloader
from swirengine.asset_streaming import AssetStreamingBudget, AssetStreamingManager
from swirengine.assets import AssetManager
from swirengine.assets17 import AsyncAssetPipeline


@dataclass(frozen=True, slots=True)
class LifecycleFinding:
    code: str
    severity: str
    detail: str


@dataclass(frozen=True, slots=True)
class RuntimeLifecycleAuditReport:
    streaming_cycles: int
    streamed_assets: int
    streaming_peak_resident_assets: int
    streaming_peak_resident_bytes: int
    streaming_final_resident_assets: int
    streaming_final_resident_bytes: int
    streaming_final_cached_paths: int
    preloader_cycles: int
    preloader_pending_after_shutdown: int
    lingering_asset_threads: tuple[str, ...]
    async_requests: int
    async_pending_after_finalize: int
    async_cached_entries: int
    async_retained_request_records: int
    async_scheduler_terminal_records: int
    findings: tuple[LifecycleFinding, ...]

    @property
    def clean(self) -> bool:
        return not self.findings

    def portable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["clean"] = self.clean
        return payload


def _asset_thread_names() -> tuple[str, ...]:
    prefixes = ("swir-assets", "swir-preload", "swir-assets17")
    return tuple(
        sorted(
            thread.name
            for thread in threading.enumerate()
            if thread.name.startswith(prefixes)
        )
    )


def _drain_streamer(streamer: AssetStreamingManager, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while streamer.diagnostics().pending:
        streamer.pump(max_completions=64)
        if time.monotonic() >= deadline:
            raise TimeoutError("asset streaming audit queue did not drain before timeout")
        time.sleep(0.001)


def _prepare_assets(root: Path, *, count: int = 32) -> AssetManager:
    root.mkdir(parents=True, exist_ok=True)
    manager = AssetManager(root)
    manager.register_loader("bin", lambda path: path.read_bytes())
    for index in range(count):
        payload = bytes([index % 251]) * (256 + (index % 7) * 31)
        (root / f"asset-{index:03d}.bin").write_bytes(payload)
    return manager


def _audit_streaming(root: Path, *, cycles: int) -> tuple[int, int, int, int, int]:
    manager = _prepare_assets(root)
    budget = AssetStreamingBudget(max_resident_bytes=4096, max_resident_assets=6)
    streamer = AssetStreamingManager(manager, budget=budget)
    try:
        for cycle in range(cycles):
            order = range(32) if cycle % 2 == 0 else range(31, -1, -1)
            for index in order:
                streamer.stage(f"asset-{index:03d}.bin")
                _drain_streamer(streamer)
                diagnostics = streamer.diagnostics()
                if diagnostics.over_budget:
                    raise AssertionError("streaming manager remained over budget after finalization")
                if diagnostics.resident_assets > budget.max_resident_assets:
                    raise AssertionError("resident asset count exceeded the configured budget")
                if diagnostics.resident_bytes > budget.max_resident_bytes:
                    raise AssertionError("resident byte count exceeded the configured budget")
        before_release = streamer.diagnostics()
        streamer.release_all(force=True)
        after_release = streamer.diagnostics()
        if after_release.resident_assets or after_release.resident_bytes:
            raise AssertionError("release_all(force=True) left resident streaming state behind")
        if manager.cached_paths():
            raise AssertionError("released streaming assets remained in the shared asset cache")
        return (
            before_release.peak_resident_assets,
            before_release.peak_resident_bytes,
            after_release.resident_assets,
            after_release.resident_bytes,
            len(manager.cached_paths()),
        )
    finally:
        streamer.shutdown(wait=True, cancel_futures=True, release_resident=True)


def _audit_preloader(root: Path, *, cycles: int) -> int:
    manager = _prepare_assets(root)
    pending_after_shutdown = 0
    for _ in range(cycles):
        preloader = AssetPreloader(manager, max_workers=4)
        futures = [preloader.load_async(f"asset-{index:03d}.bin") for index in range(32)]
        for future in futures:
            result = future.result(timeout=5.0)
            if not result.ok:
                raise AssertionError(result.error or "asset preload failed")
        preloader.shutdown(wait=True, cancel_futures=True)
        pending_after_shutdown += len(preloader.pending_paths())
    return pending_after_shutdown


def _audit_async_pipeline(root: Path, *, requests: int) -> tuple[int, int, int, int]:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "repeat.dat"
    source.write_text("runtime-lifecycle", encoding="utf-8")
    pipeline = AsyncAssetPipeline(AssetManager(root), max_workers=2, max_pending=16)
    pipeline.register_processor(
        "data",
        suffixes=[".dat"],
        decode=lambda path, _context: path.read_text(encoding="utf-8"),
    )
    try:
        for _ in range(requests):
            request = pipeline.submit(source)
            pipeline.wait_workers(timeout=5.0)
            while request.request_id in pipeline.pending_request_ids():
                pipeline.poll(max_items=16)
        diagnostics = pipeline.diagnostics()
        retained_requests = len(pipeline._records)  # noqa: SLF001 - deliberate post-release audit probe.
        scheduler_terminal = sum(
            (
                pipeline._scheduler.diagnostics().succeeded,  # noqa: SLF001
                pipeline._scheduler.diagnostics().failed,  # noqa: SLF001
                pipeline._scheduler.diagnostics().cancelled,  # noqa: SLF001
                pipeline._scheduler.diagnostics().blocked,  # noqa: SLF001
            )
        )
        return (
            diagnostics.pending,
            diagnostics.cached_entries,
            retained_requests,
            scheduler_terminal,
        )
    finally:
        pipeline.shutdown(wait=True, cancel_pending=True)


def run_runtime_lifecycle_audit(
    root: Path,
    *,
    streaming_cycles: int = 4,
    preloader_cycles: int = 4,
    async_requests: int = 96,
) -> RuntimeLifecycleAuditReport:
    if streaming_cycles < 1 or preloader_cycles < 1 or async_requests < 1:
        raise ValueError("audit cycle/request counts must all be positive")

    baseline_threads = set(_asset_thread_names())
    streaming = _audit_streaming(root / "streaming", cycles=streaming_cycles)
    preloader_pending = _audit_preloader(root / "preloader", cycles=preloader_cycles)
    async_state = _audit_async_pipeline(root / "async", requests=async_requests)

    # All owned executors above use wait=True. A short scheduler yield avoids treating a thread
    # that is finishing its Python-level teardown as a persistent lifecycle leak.
    deadline = time.monotonic() + 1.0
    lingering = tuple(name for name in _asset_thread_names() if name not in baseline_threads)
    while lingering and time.monotonic() < deadline:
        time.sleep(0.01)
        lingering = tuple(name for name in _asset_thread_names() if name not in baseline_threads)

    findings: list[LifecycleFinding] = []
    if preloader_pending:
        findings.append(
            LifecycleFinding(
                code="preloader_pending_after_shutdown",
                severity="high",
                detail=f"{preloader_pending} pending paths remained after owned shutdown",
            )
        )
    if lingering:
        findings.append(
            LifecycleFinding(
                code="asset_worker_threads_lingering",
                severity="high",
                detail=f"owned asset worker threads remained alive: {', '.join(lingering)}",
            )
        )
    if async_state[0]:
        findings.append(
            LifecycleFinding(
                code="async_asset_pending_after_finalize",
                severity="high",
                detail=f"{async_state[0]} requests remained pending after explicit finalization",
            )
        )
    if async_state[2] >= async_requests:
        findings.append(
            LifecycleFinding(
                code="async_asset_terminal_records_retained",
                severity="medium",
                detail=(
                    f"{async_state[2]} finalized AsyncAssetPipeline request records remain retained; "
                    "the public pipeline currently has no creator-facing reclamation API"
                ),
            )
        )

    return RuntimeLifecycleAuditReport(
        streaming_cycles=streaming_cycles,
        streamed_assets=32 * streaming_cycles,
        streaming_peak_resident_assets=streaming[0],
        streaming_peak_resident_bytes=streaming[1],
        streaming_final_resident_assets=streaming[2],
        streaming_final_resident_bytes=streaming[3],
        streaming_final_cached_paths=streaming[4],
        preloader_cycles=preloader_cycles,
        preloader_pending_after_shutdown=preloader_pending,
        lingering_asset_threads=lingering,
        async_requests=async_requests,
        async_pending_after_finalize=async_state[0],
        async_cached_entries=async_state[1],
        async_retained_request_records=async_state[2],
        async_scheduler_terminal_records=async_state[3],
        findings=tuple(findings),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit SwirEngine 2.0 runtime resource lifecycle")
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--streaming-cycles", type=int, default=4)
    parser.add_argument("--preloader-cycles", type=int, default=4)
    parser.add_argument("--async-requests", type=int, default=96)
    args = parser.parse_args()

    if args.workspace is None:
        with tempfile.TemporaryDirectory(prefix="swirengine-lifecycle-") as temporary:
            report = run_runtime_lifecycle_audit(
                Path(temporary),
                streaming_cycles=args.streaming_cycles,
                preloader_cycles=args.preloader_cycles,
                async_requests=args.async_requests,
            )
    else:
        report = run_runtime_lifecycle_audit(
            args.workspace,
            streaming_cycles=args.streaming_cycles,
            preloader_cycles=args.preloader_cycles,
            async_requests=args.async_requests,
        )

    print(json.dumps(report.portable(), indent=2, sort_keys=True))
    return 0 if not any(item.severity == "high" for item in report.findings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
