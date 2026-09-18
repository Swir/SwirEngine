from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from swirengine.asset_streaming import AssetStreamingBudget, AssetStreamingManager
from swirengine.assets import AssetManager
from swirengine.graphics.batching import SpriteBatch, SpriteBatchKey
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.instancing import Frustum3D, FrustumPlane
from swirengine.graphics.primitives import Cube3D, Sprite2D, TileMap2D
from swirengine.graphics.renderer2d_power import Renderer2DPowerPass
from swirengine.math.types import Vec3
from swirengine.render_resources18 import RenderResourceDescriptor, TransientRenderResourcePool
from swirengine.scene_visibility import SceneVisibilityIndex3D


class _Renderer2DHost:
    width = 1280
    height = 720

    @staticmethod
    def _center(obj, camera):
        if obj.screen_space:
            return float(obj.x), float(obj.y)
        return float(obj.x) - camera.x, float(obj.y) - camera.y


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


def _verify_2d_workload() -> tuple[int, int, int]:
    tilemap = TileMap2D("tiles.png", 128, 128, 16, 16, 4, 4).fill(1)
    visible = tuple(tilemap.iter_visible_sprites(1024, 1024, 1280, 720, zoom=1.0))
    candidates = tilemap.diagnostics.last_visibility_candidates
    if tilemap.tile_count != 16_384:
        raise RuntimeError("unexpected 2D production workload size")
    if candidates > 500 or candidates >= tilemap.tile_count // 16:
        raise RuntimeError(
            "2D tilemap visibility regressed to world-scale work: "
            f"tiles={tilemap.tile_count}, candidates={candidates}"
        )
    if len(visible) != tilemap.diagnostics.last_visible_sprites:
        raise RuntimeError("2D tilemap visibility diagnostics disagree with result")

    sprites = tuple(
        Sprite2D("tiles.png", x=float(index % 64), y=float(index // 64), width=16, height=16)
        for index in range(4096)
    )
    batch = SpriteBatch(SpriteBatchKey("tiles.png", 0, False), sprites)
    power = Renderer2DPowerPass(initial_sprite_capacity=4096)
    host = _Renderer2DHost()
    camera = Camera2D()
    initial_identity = power.staging_identity
    for _ in range(32):
        vertices = power._sprite_vertices(host, batch, 16, 16, camera)
        if vertices.shape != (4096 * 6, 8):
            raise RuntimeError(f"unexpected 2D sprite staging shape: {vertices.shape}")
    if power.staging_identity != initial_identity or power.staging_reallocations != 0:
        raise RuntimeError("2D sprite staging reallocated during a stable production workload")
    return tilemap.tile_count, candidates, len(visible)


def _box_frustum(extent: float) -> Frustum3D:
    value = float(extent)
    return Frustum3D(
        (
            FrustumPlane(1.0, 0.0, 0.0, value),
            FrustumPlane(-1.0, 0.0, 0.0, value),
            FrustumPlane(0.0, 1.0, 0.0, value),
            FrustumPlane(0.0, -1.0, 0.0, value),
            FrustumPlane(0.0, 0.0, 1.0, value),
            FrustumPlane(0.0, 0.0, -1.0, value),
        )
    )


def _verify_3d_workload() -> tuple[int, int, float]:
    index = SceneVisibilityIndex3D(leaf_size=8)
    for x in range(-32, 32):
        for z in range(-32, 32):
            index.add(Cube3D(position=Vec3(float(x * 20), 0.0, float(z * 20))))
    result = index.query(_box_frustum(6.0), refresh_dynamic=False)
    diag = result.diagnostics
    if diag.source_entries != 4096 or diag.static_entries != 4096:
        raise RuntimeError(f"unexpected 3D workload inventory: {diag}")
    if len(result.visible) != 1:
        raise RuntimeError(f"unexpected sparse-scene visibility result: {len(result.visible)}")
    if diag.leaf_tests >= 128 or diag.object_test_reduction <= 0.96:
        raise RuntimeError(
            "3D scene visibility pruning regressed: "
            f"leaf_tests={diag.leaf_tests}, reduction={diag.object_test_reduction:.4f}"
        )
    return diag.source_entries, diag.leaf_tests, diag.object_test_reduction


def main() -> int:
    with TemporaryDirectory(prefix="swir-runtime-scale-") as temp:
        streaming = _verify_streaming(Path(temp))
    render = _verify_render_pool()
    workload_2d = _verify_2d_workload()
    workload_3d = _verify_3d_workload()
    print(
        "SwirEngine 2.0 runtime scalability OK: "
        f"streaming_resident={streaming[0]}, streaming_evictions={streaming[1]}, "
        f"streaming_peak={streaming[2]}, render_creates={render[0]}, "
        f"render_reuses={render[1]}, render_peak={render[2]}, "
        f"2d_tiles={workload_2d[0]}, 2d_candidates={workload_2d[1]}, "
        f"2d_visible={workload_2d[2]}, 3d_objects={workload_3d[0]}, "
        f"3d_leaf_tests={workload_3d[1]}, 3d_reduction={workload_3d[2]:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
