from __future__ import annotations

from pathlib import Path

from demo_projects.neon_frontier_1_4.run_game import run_headless_probe
from tools.verify_1_4_release_candidate import TARGET_VERSION, audit, parse_roadmap

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_CURRENT_SOURCE_VERSIONS = {TARGET_VERSION, "1.5.0", "2.0.0", "2.1.0"}


def test_locked_1_4_contract_is_complete_on_supported_stable_lines() -> None:
    report = audit(ROOT, require_complete=True)

    assert TARGET_VERSION == "1.4.0"
    assert report.version in SUPPORTED_CURRENT_SOURCE_VERSIONS
    assert report.roadmap.total == 10
    assert report.roadmap.completed == 10
    assert report.roadmap.remaining == 0
    assert report.roadmap.percent == 100.0
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


def test_locked_hardening_workflow_keeps_real_render_packaging_and_performance_gates() -> None:
    workflow = (ROOT / ".github/workflows/showcase-hardening-1-4.yml").read_text(
        encoding="utf-8"
    )

    assert "verify_1_4_release_candidate.py --require-complete" in workflow
    assert "benchmark_showcase_1_4.py" in workflow
    assert "xvfb-run" in workflow
    assert "SWIR_1_4_SMOKE_FRAMES" in workflow
    assert "PyInstaller" in workflow
    assert "NeonFrontier14.exe" in workflow
    assert "SWIR_DEMO_RUNTIME_PROBE" in workflow


def test_historical_1_4_tag_bridge_only_targets_exact_verified_main_commit() -> None:
    workflow = (ROOT / ".github/workflows/tag-1-4.yml").read_text(encoding="utf-8")
    trigger_section = workflow.split("jobs:", 1)[0]

    assert 'branches:\n      - "release/1.4.0-publish"' in trigger_section
    assert "verify_1_4_release_candidate.py --require-complete" in workflow
    assert "git/ref/heads/main" in workflow
    assert "refs/tags/v1.4.0" in workflow
    assert "contents: write" in workflow
    assert "pypa/gh-action-pypi-publish" not in workflow
    assert "main_sha" in workflow
    assert "GITHUB_SHA" in workflow


def test_current_release_workflow_preserves_trusted_publisher_without_rewriting_history() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    trigger_section = workflow.split("jobs:", 1)[0]

    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "id-token: write" in workflow
    assert "environment: pypi" in workflow
    assert "skip-existing: true" not in workflow
    assert "workflow_dispatch:" in trigger_section
    assert "RELEASE_TAG: v2.0.0" in trigger_section
    assert "RELEASE_SHA: 4c219f3bed4c107c612a58fa2fb1f1362b4dfc46" in trigger_section
    assert 'ref: "refs/tags/v2.0.0"' in workflow
    assert "git push --force" not in workflow
    assert "git tag -f" not in workflow


def test_current_metadata_remains_compatible_with_locked_1_4_artifacts() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init_text = (ROOT / "src/swirengine/__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notes = (ROOT / "RELEASE_NOTES_1_4.md").read_text(encoding="utf-8")

    assert any(
        f'version = "{version}"' in pyproject for version in SUPPORTED_CURRENT_SOURCE_VERSIONS
    )
    assert any(
        f'__version__ = "{version}"' in init_text for version in SUPPORTED_CURRENT_SOURCE_VERSIONS
    )
    assert "`v1.4.0`" in readme
    assert "| 1.4 |" in readme
    assert "released/locked" in readme
    assert "10/10 = 100.0%" in readme
    assert notes.startswith("# SwirEngine 1.4.0 Release Notes")
