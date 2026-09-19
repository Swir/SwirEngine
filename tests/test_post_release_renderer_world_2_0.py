from __future__ import annotations

from tools.audit_renderer_world_2_0 import run_renderer_world_audit


def test_renderer_world_audit_keeps_production_residency_bounded() -> None:
    report = run_renderer_world_audit(
        render_cycles=96,
        shader_requests=24,
        terrain_steps=32,
        world_steps=80,
    )

    assert report.clean
    assert report.render_peak_resident_resources <= 4
    assert report.render_peak_resident_bytes <= 4096
    assert report.render_final_resident_resources == 0
    assert report.render_final_resident_bytes == 0
    assert report.render_evictions > 0
    assert report.shader_cached_entries <= 8
    assert report.shader_pending == 0
    assert report.shader_forgotten_requests == report.shader_requests
    assert report.terrain_max_cached_meshes <= 12
    assert report.terrain_max_selected_chunks <= 9
    assert report.terrain_cache_hits > 0
    assert report.world_max_candidate_keys == 9
    assert report.world_max_tracked_chunks <= 10
    assert report.world_total_unloads > 0
    assert report.world_final_tracked_chunks == 0


def test_renderer_world_audit_is_repeatable_without_retained_process_state() -> None:
    first = run_renderer_world_audit(
        render_cycles=48,
        shader_requests=12,
        terrain_steps=16,
        world_steps=40,
    )
    second = run_renderer_world_audit(
        render_cycles=48,
        shader_requests=12,
        terrain_steps=16,
        world_steps=40,
    )

    assert first.clean and second.clean
    assert first.render_final_resident_resources == second.render_final_resident_resources == 0
    assert first.render_final_resident_bytes == second.render_final_resident_bytes == 0
    assert first.shader_pending == second.shader_pending == 0
    assert first.world_final_tracked_chunks == second.world_final_tracked_chunks == 0
    assert first.terrain_max_cached_meshes == second.terrain_max_cached_meshes
    assert first.world_max_tracked_chunks == second.world_max_tracked_chunks
