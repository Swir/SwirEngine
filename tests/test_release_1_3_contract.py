from __future__ import annotations

from pathlib import Path

from tools.verify_1_3_release_candidate import audit, parse_roadmap

ROOT = Path(__file__).resolve().parents[1]


def test_current_1_3_development_contract_is_valid() -> None:
    report = audit(ROOT)

    assert report.version in {"1.2.0", "1.3.0"}
    assert report.roadmap.total == 10
    assert report.roadmap.completed in {9, 10}


def test_roadmap_parser_derives_exact_twenty_segment_bar() -> None:
    state = parse_roadmap("\n".join(["- [x] done"] * 9 + ["- [ ] remaining"]))

    assert state.completed == 9
    assert state.remaining == 1
    assert state.total == 10
    assert state.percent == 90.0
    assert state.bar == "██████████████████░░ 90.0%"


def test_final_game_contract_mentions_every_integrated_1_3_system() -> None:
    source = (ROOT / "demo_projects/neon_frontier_1_3/run_game.py").read_text(encoding="utf-8")

    required = {
        "InstancedCube3D",
        "ShaderMesh3D",
        "CollisionWorld3D",
        "NavigationGrid3D",
        "LargeWorldStreamer",
        "GameplayRuntime",
        "SWIR_1_3_SMOKE_FRAMES",
        "SWIR_DEMO_RUNTIME_PROBE",
    }
    assert required <= set(source.split()) | {token for token in required if token in source}


def test_release_workflow_is_hard_gated_on_complete_1_3_contract() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "verify_1_3_release_candidate.py --require-complete" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "id-token: write" in workflow
    assert "skip-existing: true" not in workflow


def test_full_game_workflow_has_real_opengl_and_packaged_windows_probe() -> None:
    workflow = (ROOT / ".github/workflows/full-game-1-3.yml").read_text(encoding="utf-8")

    assert "xvfb-run" in workflow
    assert "SWIR_1_3_SMOKE_FRAMES" in workflow
    assert "PyInstaller" in workflow
    assert "SWIR_DEMO_RUNTIME_PROBE" in workflow
    assert "NeonFrontier13.exe" in workflow
