from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from swirengine.core.scene import Scene
from swirengine.large_world import (
    ChunkContent,
    ChunkDefinition,
    ChunkKey,
    LargeWorldSettings,
    LargeWorldStreamer,
)
from swirengine.render_resources18 import RenderResourceDescriptor, TransientRenderResourcePool
from swirengine.shader_cache17 import ShaderMaterialPreparationCache
from swirengine.terrain import HeightmapTerrain, TerrainConfig

_VERTEX = "#version 330\nvoid main() { gl_Position = vec4(0.0); }"
_FRAGMENT = "#version 330\nout vec4 color; void main() { color = vec4(1.0); }"


@dataclass(frozen=True, slots=True)
class RendererWorldAuditReport:
    render_cycles: int
    render_creates: int
    render_reuses: int
    render_evictions: int
    render_peak_resident_resources: int
    render_peak_resident_bytes: int
    render_final_resident_resources: int
    render_final_resident_bytes: int
    shader_requests: int
    shader_cached_entries: int
    shader_cache_evictions: int
    shader_pending: int
    shader_forgotten_requests: int
    terrain_steps: int
    terrain_max_cached_meshes: int
    terrain_cache_hits: int
    terrain_mesh_builds: int
    terrain_max_selected_chunks: int
    world_steps: int
    world_max_tracked_chunks: int
    world_max_candidate_keys: int
    world_total_unloads: int
    world_final_tracked_chunks: int

    @property
    def clean(self) -> bool:
        return (
            self.render_final_resident_resources == 0
            and self.render_final_resident_bytes == 0
            and self.render_peak_resident_resources <= 4
            and self.render_peak_resident_bytes <= 4096
            and self.shader_cached_entries <= 8
            and self.shader_pending == 0
            and self.shader_forgotten_requests == self.shader_requests
            and self.terrain_max_cached_meshes <= 12
            and self.terrain_max_selected_chunks <= 9
            and self.world_max_tracked_chunks <= 10
            and self.world_max_candidate_keys == 9
            and self.world_final_tracked_chunks == 0
        )

    def portable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["clean"] = self.clean
        return payload


def _audit_render_resources(cycles: int) -> dict[str, int]:
    created: list[dict[str, int]] = []
    destroyed: list[dict[str, int]] = []

    def create(_descriptor: RenderResourceDescriptor) -> dict[str, int]:
        resource = {"id": len(created) + 1}
        created.append(resource)
        return resource

    def destroy(resource: dict[str, int]) -> None:
        destroyed.append(resource)

    pool = TransientRenderResourcePool(
        create=create,
        destroy=destroy,
        max_resources=4,
        max_bytes=4096,
    )
    descriptors = tuple(
        RenderResourceDescriptor(
            "texture",
            f"rgba8-{index}",
            16,
            16,
            size_bytes=1024,
        )
        for index in range(6)
    )
    try:
        for index in range(cycles):
            lease = pool.acquire(descriptors[index % len(descriptors)])
            pool.release(lease.handle)
            diagnostics = pool.diagnostics()
            if diagnostics.resident_resources > 4 or diagnostics.resident_bytes > 4096:
                raise AssertionError("transient render pool exceeded its configured residency budget")
        before_close = pool.diagnostics()
    finally:
        pool.close()
    after_close = pool.diagnostics()
    if len(destroyed) != len(created):
        raise AssertionError("transient render pool did not destroy every created resource")
    return {
        "creates": before_close.creates,
        "reuses": before_close.reuses,
        "evictions": before_close.evictions,
        "peak_resources": before_close.peak_resident_resources,
        "peak_bytes": before_close.peak_resident_bytes,
        "final_resources": after_close.resident_resources,
        "final_bytes": after_close.resident_bytes,
    }


def _audit_shader_cache(requests: int) -> dict[str, int]:
    cache = ShaderMaterialPreparationCache(
        max_workers=2,
        max_pending=16,
        max_requests=16,
        max_cache_entries=8,
    )
    forgotten = 0
    try:
        for index in range(requests):
            request = cache.submit(
                {
                    "vertex": _VERTEX,
                    "fragment": _FRAGMENT + f"\n// audit variant {index % 12}",
                },
                defines={"QUALITY": index % 3},
                material={"roughness": (index % 5) / 4.0},
                finalize=lambda prepared: prepared.source_fingerprint,
            )
            cache.wait_workers(timeout=2.0)
            outcomes = cache.poll(max_items=16)
            result = next(item for item in outcomes if item.request_id == request.request_id)
            if not result.successful:
                raise AssertionError(f"shader/material audit request failed: {result.error_type}")
            cache.forget(request.request_id)
            forgotten += 1
            diagnostics = cache.diagnostics()
            if diagnostics.pending != 0:
                raise AssertionError("shader/material audit retained pending work after finalization")
            if diagnostics.cached_entries > cache.max_cache_entries:
                raise AssertionError("shader/material cache exceeded max_cache_entries")
        diagnostics = cache.diagnostics()
        return {
            "cached_entries": diagnostics.cached_entries,
            "evictions": diagnostics.cache_evictions_total,
            "pending": diagnostics.pending,
            "forgotten": forgotten,
        }
    finally:
        cache.shutdown()


def _audit_terrain(steps: int) -> dict[str, int]:
    terrain = HeightmapTerrain(
        np.zeros((257, 257), dtype="f4"),
        config=TerrainConfig(
            chunk_cells=16,
            lod_steps=(1, 2, 4),
            lod_distances=(24.0, 64.0),
            mesh_cache_size=12,
        ),
    )
    max_cached = 0
    max_selected = 0
    positions = tuple(
        (8.0 + (index % 8) * 32.0, 8.0 + ((index // 8) % 4) * 64.0)
        for index in range(max(1, steps // 2))
    )
    for index in range(steps):
        x, z = positions[index % len(positions)]
        selected = terrain.select_chunks(x, z, radius_chunks=1)
        diagnostics = terrain.diagnostics
        max_cached = max(max_cached, diagnostics.cached_meshes)
        max_selected = max(max_selected, len(selected))
        if diagnostics.cached_meshes > terrain.config.mesh_cache_size:
            raise AssertionError("terrain mesh cache exceeded its configured entry budget")
    diagnostics = terrain.diagnostics
    return {
        "max_cached": max_cached,
        "cache_hits": diagnostics.cache_hits,
        "mesh_builds": diagnostics.mesh_builds,
        "max_selected": max_selected,
    }


def _audit_large_world(steps: int) -> dict[str, int]:
    scene = Scene()

    def provider(key: ChunkKey) -> ChunkDefinition:
        return ChunkDefinition(key, lambda _context: ChunkContent())

    world = LargeWorldStreamer(
        scene,
        provider,
        settings=LargeWorldSettings(
            chunk_size=8.0,
            dimensions=2,
            active_radius_chunks=0,
            preload_radius_chunks=1,
            retention_radius_chunks=2,
            max_activations_per_update=2,
            max_deactivations_per_update=16,
        ),
    )
    max_tracked = 0
    max_candidates = 0
    for step in range(steps):
        result = world.update(
            (step * 80.0, 0.0),
            visibility=lambda context, _definition: context.key.x % 2 == 0,
        )
        max_tracked = max(max_tracked, result.diagnostics.tracked_chunks)
        max_candidates = max(max_candidates, result.diagnostics.candidate_keys)
        if result.diagnostics.tracked_chunks > 10:
            raise AssertionError("large-world streaming accumulated state outside its retention window")
    total_unloads = world.diagnostics.total_unloads
    world.unload_all()
    return {
        "max_tracked": max_tracked,
        "max_candidates": max_candidates,
        "total_unloads": total_unloads,
        "final_tracked": len(world.tracked_keys),
    }


def run_renderer_world_audit(
    *,
    render_cycles: int = 512,
    shader_requests: int = 96,
    terrain_steps: int = 96,
    world_steps: int = 250,
) -> RendererWorldAuditReport:
    if min(render_cycles, shader_requests, terrain_steps, world_steps) < 1:
        raise ValueError("audit workload counts must all be positive")

    render = _audit_render_resources(render_cycles)
    shader = _audit_shader_cache(shader_requests)
    terrain = _audit_terrain(terrain_steps)
    world = _audit_large_world(world_steps)
    report = RendererWorldAuditReport(
        render_cycles=render_cycles,
        render_creates=render["creates"],
        render_reuses=render["reuses"],
        render_evictions=render["evictions"],
        render_peak_resident_resources=render["peak_resources"],
        render_peak_resident_bytes=render["peak_bytes"],
        render_final_resident_resources=render["final_resources"],
        render_final_resident_bytes=render["final_bytes"],
        shader_requests=shader_requests,
        shader_cached_entries=shader["cached_entries"],
        shader_cache_evictions=shader["evictions"],
        shader_pending=shader["pending"],
        shader_forgotten_requests=shader["forgotten"],
        terrain_steps=terrain_steps,
        terrain_max_cached_meshes=terrain["max_cached"],
        terrain_cache_hits=terrain["cache_hits"],
        terrain_mesh_builds=terrain["mesh_builds"],
        terrain_max_selected_chunks=terrain["max_selected"],
        world_steps=world_steps,
        world_max_tracked_chunks=world["max_tracked"],
        world_max_candidate_keys=world["max_candidates"],
        world_total_unloads=world["total_unloads"],
        world_final_tracked_chunks=world["final_tracked"],
    )
    if not report.clean:
        raise AssertionError(f"renderer/world audit failed: {report.portable()}")
    return report


def main() -> int:
    report = run_renderer_world_audit()
    print(json.dumps(report.portable(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
