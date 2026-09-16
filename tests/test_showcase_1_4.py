from __future__ import annotations

from demo_projects.showcase_1_4.run_game import run_showcase


def test_showcase_integrates_1_4_world_authoring_and_multiplayer_paths() -> None:
    report = run_showcase()

    assert report.terrain_chunks > 0
    assert report.streamed_objects > 0
    assert report.controller_x > 1.0
    assert report.editor_selection == 1
    assert report.editor_cube_x == 1.25
    assert report.particle_capacity == 4096
    assert report.particle_queued > 0
    assert report.snapshot_bytes > 0
    # Tiny single-entity packets can make delta framing larger than a full snapshot.
    # Sparse-delta bandwidth savings are enforced by the dedicated Multiplayer 2.0 workload.
    assert report.delta_bytes > 0
    assert report.interpolated_x > 0.0
