from __future__ import annotations

from pathlib import Path

import pytest

from tools.verify_1_4_release_candidate import audit, parse_roadmap

ROOT = Path(__file__).resolve().parents[1]


def test_current_1_4_development_contract_is_exactly_nine_of_ten() -> None:
    report = audit(ROOT)

    assert report.version == "1.3.0"
    assert report.roadmap.completed == 9
    assert report.roadmap.remaining == 1
    assert report.roadmap.total == 10
    assert report.roadmap.percent == 90.0
    assert report.roadmap.bar == "██████████████████░░ 90.0%"
    assert report.status_complete is False
    assert report.final_showcase_present is True
    assert report.release_ready is False


def test_incomplete_1_4_contract_refuses_release_mode() -> None:
    with pytest.raises(ValueError, match="exactly 10/10"):
        audit(ROOT, require_complete=True)


def test_roadmap_parser_derives_exact_twenty_segment_bar() -> None:
    state = parse_roadmap("\n".join(["- [x] done"] * 9 + ["- [ ] todo"]))

    assert state.completed == 9
    assert state.remaining == 1
    assert state.total == 10
    assert state.percent == 90.0
    assert state.bar == "██████████████████░░ 90.0%"


def test_release_readiness_workflow_is_non_publishing_and_covers_1_4_gates() -> None:
    workflow = (ROOT / ".github/workflows/release-readiness-1-4.yml").read_text(encoding="utf-8")

    required = {
        "verify_1_4_release_candidate.py",
        "python -m build",
        "python -m twine check",
        "benchmark_terrain_world_lod.py",
        "benchmark_physics2_1_4.py",
        "benchmark_character_controllers_1_4.py",
        "benchmark_renderer2_1_4.py",
        "benchmark_gpu_particles_1_4.py",
        "benchmark_asset_pipeline_1_4.py",
        "benchmark_scene_visibility_1_4.py",
        "benchmark_editor_authoring_1_4.py",
        "benchmark_multiplayer_2_1_4.py",
        "smoke_renderer2_gl.py",
        "smoke_gpu_particles_gl.py",
        "smoke_scene_acceleration_gl.py",
        "demo_projects/showcase_1_4/run_game.py",
        "SWIR_1_4_SHOWCASE_RENDER",
    }
    assert all(token in workflow for token in required)
    assert "gh-action-pypi-publish" not in workflow
    assert "gh release create" not in workflow


def test_cross_platform_ci_runs_active_1_4_development_audit() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "Verify locked 1.3 release contract" in workflow
    assert "python tools/verify_1_3_release_candidate.py" in workflow
    assert "Verify active 1.4 development contract" in workflow
    assert "python tools/verify_1_4_release_candidate.py" in workflow
