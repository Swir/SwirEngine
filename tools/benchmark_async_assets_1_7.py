from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from swirengine.assets import AssetManager
from swirengine.assets17 import AsyncAssetPipeline

ASSET_COUNT = 512
TIME_BUDGET_SECONDS = 5.0


def _drain(pipeline: AsyncAssetPipeline) -> None:
    while pipeline.pending_request_ids():
        pipeline.poll(max_items=64)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="swirengine-assets17-") as temporary:
        root = Path(temporary)
        for index in range(ASSET_COUNT):
            (root / f"asset-{index:04d}.dat").write_bytes(
                f"payload:{index:04d}".encode("ascii")
            )

        pipeline = AsyncAssetPipeline(
            AssetManager(root),
            max_workers=4,
            max_pending=ASSET_COUNT * 2 + 8,
        )
        pipeline.register_processor(
            "data",
            suffixes=[".dat"],
            decode=lambda path, context: (
                context.raise_if_cancelled(),
                path.read_bytes(),
            )[1],
            cook=lambda value, _context: value[::-1],
        )

        started = perf_counter()
        for index in range(ASSET_COUNT):
            pipeline.submit(f"asset-{index:04d}.dat")
        pipeline.wait_workers(timeout=TIME_BUDGET_SECONDS)
        _drain(pipeline)

        for index in range(ASSET_COUNT):
            pipeline.submit(f"asset-{index:04d}.dat")
        pipeline.wait_workers(timeout=TIME_BUDGET_SECONDS)
        _drain(pipeline)
        elapsed = perf_counter() - started
        diagnostics = pipeline.diagnostics()
        pipeline.shutdown(wait=True, cancel_pending=True)

    expected = ASSET_COUNT * 2
    if diagnostics.completed_total != expected:
        raise SystemExit(
            f"expected {expected} completions, got {diagnostics.completed_total}"
        )
    if diagnostics.cache_misses_total != ASSET_COUNT:
        raise SystemExit("first pass did not account for exactly one cache miss per asset")
    if diagnostics.cache_hits_total != ASSET_COUNT:
        raise SystemExit("second pass did not account for exactly one cache hit per asset")
    if elapsed >= TIME_BUDGET_SECONDS:
        raise SystemExit(
            f"async asset workload took {elapsed:.4f}s; budget is {TIME_BUDGET_SECONDS:.1f}s"
        )

    print(
        "Async Asset Decode/Cook 1.7 workload: "
        f"{expected} requests ({ASSET_COUNT} cold + {ASSET_COUNT} cached) "
        f"in {elapsed:.4f}s; budget {TIME_BUDGET_SECONDS:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
