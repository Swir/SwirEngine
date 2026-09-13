from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns, sleep

from swirengine.asset_pipeline import AssetPreloader
from swirengine.assets import AssetManager


def run(count: int, delay_ms: float, workers: int) -> tuple[int, int, float]:
    with TemporaryDirectory(prefix="swir-preload-bench-") as temp_dir:
        root = Path(temp_dir)
        for index in range(count):
            (root / f"asset-{index}.txt").write_text(str(index), encoding="utf-8")

        def loader(path: Path) -> str:
            sleep(delay_ms / 1000.0)
            return path.read_text(encoding="utf-8")

        serial_assets = AssetManager(root)
        serial_assets.register_loader("txt", loader)
        started = perf_counter_ns()
        for index in range(count):
            serial_assets.load(f"asset-{index}.txt")
        serial_ns = perf_counter_ns() - started

        parallel_assets = AssetManager(root)
        parallel_assets.register_loader("txt", loader)
        with AssetPreloader(parallel_assets, max_workers=workers) as preloader:
            report = preloader.preload(f"asset-{index}.txt" for index in range(count))
        parallel_ns = report.wall_time_ns

    improvement = 0.0 if serial_ns <= 0 else 1.0 - (parallel_ns / serial_ns)
    return serial_ns, parallel_ns, improvement


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark SwirEngine async asset preload wait time")
    parser.add_argument("--assets", type=int, default=16)
    parser.add_argument("--delay-ms", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--assert-win", action="store_true")
    args = parser.parse_args()

    if args.assets < 1 or args.delay_ms < 0 or args.workers < 1:
        parser.error("assets/workers must be positive and delay-ms must be non-negative")

    serial_ns, parallel_ns, improvement = run(args.assets, args.delay_ms, args.workers)
    print(f"assets={args.assets} workers={args.workers} artificial_delay_ms={args.delay_ms:.3f}")
    print(f"serial_wait_ns={serial_ns}")
    print(f"preload_wait_ns={parallel_ns}")
    print(f"wait_reduction={improvement:.2%}")

    if args.assert_win and args.assets >= 2 and args.workers >= 2 and args.delay_ms >= 2.0:
        # Deliberately loose gate: we only need proof that overlapped I/O-like work beats serialized
        # loading, not a machine-specific speedup promise.
        if parallel_ns >= serial_ns * 0.85:
            raise SystemExit("async preload did not demonstrate the expected wait reduction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
