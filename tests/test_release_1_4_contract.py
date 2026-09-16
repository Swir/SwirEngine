from __future__ import annotations

from pathlib import Path

from demo_projects.neon_frontier_1_4.run_game import run_headless_probe
from tools.verify_1_4_release_candidate import audit, parse_roadmap

ROOT = Path(__file__).resolve().parents[1]


def test_current_1_4_hardening_contract_is_consistent() -> None:
    report = audit(ROOT)

    assert report.roadmap.total == 10
    assert report.roadmap.completed in {9, 10}
    assert report.roadmap.remaining in {0, 1}
    assert report.roadmap.percent in {90.0, 100.0}
    if report.roadmap.completed == 9:
        assert report.version == "1.3.0"
        assert report.roadmap.bar == "██████████████████░░ 90.0%"
    else:
        assert report.version in {"1.3.0", "1.4.0"}
        assert report.roadmap.bar == "████████████████████ 100.0%"


def test_roadmap_parser_derives_exact_twenty_segment_bars() -> None:
    active = parse_roadmap("\n".join(["- [x] done"] * 9 + ["- [ ] pending"]))
    complete = parse_roadmap("\n".join(["- [x] done"] * 10))

    assert active.bar == "██████████████████░░ 90.0%"
    assert complete.bar == "████████████████████ 100.0%"


def test_integrated_headless_showcase_exercises_every_final_system() -> None:
    report = run_headless_probe()

    assert report.terrain_chunks >= 1
    assert report.terrain_triangles > 0
    assert report.streamed_chunks >= 1
    assert report.physics_bodies >= 2
    assert report.character_sweeps >= 1
    assert report.renderer_passes >= 4
    assert report.renderer_draw_calls >= 1
    assert report.particle_emitted >= 512
    assert report.editor_targets == 2
    assert report.network_delta_entities == 1
    assert report.network_bytes > 0


def test_showcase_source_covers_all_1_4_integration_paths() -> None:
    source = (ROOT / "demo_projects/neon_frontier_1_4/run_game.py").read_text(encoding="utf-8")
    required = {
        "HeightmapTerrain",
        "PhysicsScene3D",
        "CharacterController3D",
        "configure_renderer2",
        "gpu_particles",
        "LargeWorldStreamer",
        "EditorAuthoringWorkspace",
        "SnapshotDelta",
    }
    assert all(token in source for token in required)


def test_final_hardening_workflow_has_real_render_packaging_and_performance_gates() -> None:
    workflow = (ROOT / ".github/workflows/showcase-hardening-1-4.yml").read_text(encoding="utf-8")

    assert "verify_1_4_release_candidate.py" in workflow
    assert "benchmark_showcase_1_4.py" in workflow
    assert "xvfb-run" in workflow
    assert "SWIR_1_4_SMOKE_FRAMES" in workflow
    assert "PyInstaller" in workflow
    assert "NeonFrontier14.exe" in workflow
    assert "SWIR_DEMO_RUNTIME_PROBE" in workflow
