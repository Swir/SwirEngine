from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from swirengine.asset_streaming import AssetStreamingBudget, AssetStreamingManager
from swirengine.assets import AssetManager
from swirengine.render_resources18 import RenderResourceDescriptor, TransientRenderResourcePool


def _drain(streamer: AssetStreamingManager) -> None:
    for _ in range(200):
        streamer.pump(max_completions=64)
        if streamer.diagnostics().pending == 0:
            return
        sleep(0.002)
    raise RuntimeError("streaming verifier timed out while draining background work")


def _verify_streaming(root: Path) -> tuple[int, int, int]:
    assets = AssetManager(root)
    assets.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))
    for index in range(64):
        (root / f"asset-{index}.txt").write_text("x" * 128, encoding="utf-8")

    budget = AssetStreamingBudget(max_resident_bytes=16 * 128, max_resident_assets=16)
    streamer = AssetStreamingManager(assets, budget=budget)
    try:
        for cycle in range(8):
            for index in range(64):
                streamer.stage(f"asset-{(index + cycle) % 64}.txt")
                if index % 8 == 7:
                    _drain(streamer)
                    diag = streamer.diagnostics()
                    if diag.over_budget:
                        raise RuntimeError("unpinned streaming workload exceeded its residency budget")
                    if diag.resident_assets > 16 or diag.resident_bytes > 16 * 128:
                        raise RuntimeError("streaming residency escaped configured bounds")
        _drain(streamer)
        diag = streamer.diagnostics()
        resident = diag.resident_assets
        evictions = diag.evictions
        peak = diag.peak_resident_assets
        if diag.failed or diag.cancelled or diag.budget_pressure_events:
            raise RuntimeError(f"unexpected streaming failure diagnostics: {diag}")
        streamer.shutdown(release_resident=True)
        closed = streamer.diagnostics()
        if closed.resident_assets or closed.resident_bytes or closed.pending:
            raise RuntimeError("streaming teardown retained session resources")
        return resident, evictions, peak
    finally:
        if not streamer.closed:
            streamer.shutdown(release_resident=True)


def _verify_render_pool() -> tuple[int, int, int]:
    created: list[object] = []
    destroyed: list[object] = []

    def create(_descriptor: RenderResourceDescriptor) -> object:
        resource = object()
        created.append(resource)
        return resource

    def destroy(resource: object) -> None:
        destroyed.append(resource)

    pool = TransientRenderResourcePool(
        create=create,
        destroy=destroy,
        max_resources=8,
        max_bytes=8 * 4096,
    )
    descriptor = RenderResourceDescriptor(
        "texture",
        "rgba8",
        32,
        32,
        size_bytes=4096,
    )
    for _ in range(5000):
        lease = pool.acquire(descriptor)
        pool.release(lease.handle)
    diag = pool.diagnostics()
    if diag.creates != 1 or diag.reuses != 4999:
        raise RuntimeError(f"render resource reuse regressed: {diag}")
    if diag.resident_resources != 1 or diag.peak_resident_resources != 1:
        raise RuntimeError(f"render residency grew unexpectedly: {diag}")
    pool.close()
    closed = pool.diagnostics()
    if closed.resident_resources or closed.resident_bytes:
        raise RuntimeError("render resource pool retained resources after close")
    if len(created) != len(destroyed):
        raise RuntimeError("render resource create/destroy lifecycle is unbalanced")
    return diag.creates, diag.reuses, diag.peak_resident_resources


def main() -> int:
    with TemporaryDirectory(prefix="swir-runtime-scale-") as temp:
        streaming = _verify_streaming(Path(temp))
    render = _verify_render_pool()
    print(
        "SwirEngine 2.0 runtime scalability OK: "
        f"streaming_resident={streaming[0]}, streaming_evictions={streaming[1]}, "
        f"streaming_peak={streaming[2]}, render_creates={render[0]}, "
        f"render_reuses={render[1]}, render_peak={render[2]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
