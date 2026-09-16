from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from time import perf_counter

from swirengine.asset_pipeline import AssetImportState, AssetPipeline
from swirengine.assets import AssetManager


def run(*, assets_count: int, workers: int) -> None:
    if assets_count < 8:
        raise ValueError("assets_count must be >= 8")
    if workers < 1:
        raise ValueError("workers must be >= 1")

    with tempfile.TemporaryDirectory(prefix="swir-asset-pipeline-") as directory:
        root = Path(directory)
        dependency = root / "shared.bin"
        dependency.write_bytes(b"shared-v1")
        for index in range(assets_count):
            (root / f"asset-{index:04d}.asset").write_text(
                f"asset-{index:04d}",
                encoding="utf-8",
            )

        manager = AssetManager(root)
        with AssetPipeline(manager, max_workers=workers) as pipeline:
            pipeline.register_processor(
                "benchmark",
                suffixes=(".asset",),
                loader=lambda path: (path.read_text(encoding="utf-8"), dependency.read_bytes()),
                dependencies=lambda _path: (dependency,),
            )

            cold_started = perf_counter()
            cold = [
                pipeline.wait(pipeline.submit(f"asset-{index:04d}.asset"), timeout=10)
                for index in range(assets_count)
            ]
            cold_seconds = perf_counter() - cold_started
            if any(result.state is not AssetImportState.COMPLETED for result in cold):
                raise RuntimeError("cold import workload did not complete")
            if any(result.cache_hit for result in cold):
                raise RuntimeError("cold import unexpectedly reported a cache hit")

            warm_started = perf_counter()
            warm = [
                pipeline.wait(pipeline.submit(f"asset-{index:04d}.asset"), timeout=10)
                for index in range(assets_count)
            ]
            warm_seconds = perf_counter() - warm_started
            if not all(result.cache_hit for result in warm):
                raise RuntimeError("warm import workload did not hit every derived cache entry")

            manager.invalidate(dependency)
            if pipeline.diagnostics.cached_entries != 0:
                raise RuntimeError("dependency invalidation did not clear transitive derived cache")

            refill_started = perf_counter()
            refill = [
                pipeline.wait(pipeline.submit(f"asset-{index:04d}.asset"), timeout=10)
                for index in range(assets_count)
            ]
            refill_seconds = perf_counter() - refill_started
            if any(result.cache_hit for result in refill):
                raise RuntimeError("refill workload unexpectedly reused invalidated cache entries")

            diagnostics = pipeline.diagnostics
            expected_completed = assets_count * 3
            if diagnostics.completed != expected_completed:
                raise RuntimeError(
                    f"expected {expected_completed} completed imports, got {diagnostics.completed}"
                )
            if diagnostics.cache_hits != assets_count:
                raise RuntimeError(
                    f"expected {assets_count} cache hits, got {diagnostics.cache_hits}"
                )
            if diagnostics.failed or diagnostics.stale or diagnostics.cancelled:
                raise RuntimeError(f"unexpected terminal diagnostics: {diagnostics}")

    print(
        "Asset Pipeline 2.0 workload gate passed: "
        f"assets={assets_count}, workers={workers}, "
        f"cold={cold_seconds:.4f}s, warm={warm_seconds:.4f}s, refill={refill_seconds:.4f}s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SwirEngine 1.4 Asset Pipeline 2.0 workload gate")
    parser.add_argument("--assets", type=int, default=128)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run(assets_count=args.assets, workers=args.workers)


if __name__ == "__main__":
    main()
