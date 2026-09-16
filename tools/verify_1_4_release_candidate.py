from __future__ import annotations

import argparse
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

EXPECTED_TOTAL = 10
TARGET_VERSION = "1.4.0"
CURRENT_STABLE_VERSION = "1.3.0"
EXPECTED_REQUIRES_PYTHON = ">=3.10,<3.15"

REQUIRED_MILESTONE_WORKFLOWS = (
    "terrain-world-lod-1-4.yml",
    "physics-2-1-4.yml",
    "character-controllers-1-4.yml",
    "renderer2-1-4.yml",
    "gpu-vfx-1-4.yml",
    "asset-pipeline-2-1-4.yml",
    "scene-acceleration-1-4.yml",
    "editor-authoring-1-4.yml",
    "multiplayer-2-1-4.yml",
)

REQUIRED_BENCHMARKS = (
    "benchmark_terrain_world_lod.py",
    "benchmark_physics2_1_4.py",
    "benchmark_character_controllers_1_4.py",
    "benchmark_renderer2_1_4.py",
    "benchmark_gpu_particles_1_4.py",
    "benchmark_asset_pipeline_1_4.py",
    "benchmark_scene_visibility_1_4.py",
    "benchmark_editor_authoring_1_4.py",
    "benchmark_multiplayer_2_1_4.py",
)

REQUIRED_DOCS = (
    "TERRAIN_WORLD_LOD_1_4.md",
    "PHYSICS_2_1_4.md",
    "CHARACTER_CONTROLLERS_1_4.md",
    "RENDERER2_1_4.md",
    "GPU_VFX_PARTICLES_1_4.md",
    "ASSET_PIPELINE_2_1_4.md",
    "EDITOR_AUTHORING_1_4.md",
    "MULTIPLAYER_2_1_4.md",
    "RELEASE_READINESS_1_4.md",
)

FINAL_ONLY_FILES = (
    "demo_projects/showcase_1_4/run_game.py",
    "docs/SHOWCASE_1_4.md",
)


@dataclass(frozen=True)
class RoadmapState:
    completed: int
    remaining: int
    total: int
    percent: float
    bar: str


@dataclass(frozen=True)
class ReleaseReadinessReport:
    version: str
    roadmap: RoadmapState
    status_complete: bool
    release_workflow_has_1_4_gate: bool
    final_showcase_present: bool
    release_ready: bool


def parse_roadmap(text: str) -> RoadmapState:
    tasks = re.findall(r"^- \[([ xX])\] ", text, flags=re.MULTILINE)
    if not tasks:
        raise ValueError("ROADMAP_1_4.md has no milestone checkboxes")
    completed = sum(item.lower() == "x" for item in tasks)
    total = len(tasks)
    remaining = total - completed
    percent = round((completed / total) * 100.0, 1)
    filled = round((completed / total) * 20)
    bar = f"{'█' * filled}{'░' * (20 - filled)} {percent:.1f}%"
    return RoadmapState(
        completed=completed,
        remaining=remaining,
        total=total,
        percent=percent,
        bar=bar,
    )


def _project_metadata(root: Path) -> dict[str, object]:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_roadmap_metadata(text: str, state: RoadmapState) -> None:
    _expect(state.total == EXPECTED_TOTAL, f"1.4 roadmap must have exactly {EXPECTED_TOTAL} milestones")
    expected_badge = f"ROADMAP-{state.percent:.1f}%25"
    expected_done = f"DONE-{state.completed}%2F{state.total}"
    expected_dashboard = (
        f"| **{state.completed}** | **{state.remaining}** | **{state.total}** | "
        f"**{state.percent:.1f}%** |"
    )
    _expect(expected_badge in text, f"roadmap badge is stale; expected {expected_badge}")
    _expect(expected_done in text, f"roadmap DONE badge is stale; expected {expected_done}")
    _expect(state.bar in text, f"roadmap progress bar is stale; expected {state.bar}")
    _expect(expected_dashboard in text, "roadmap dashboard is stale")


def _require_files(root: Path, paths: tuple[str, ...], label: str) -> None:
    missing = [path for path in paths if not (root / path).is_file()]
    _expect(not missing, f"missing {label}: {', '.join(missing)}")


def audit(root: Path, *, require_complete: bool = False) -> ReleaseReadinessReport:
    root = root.resolve()
    roadmap_path = root / "ROADMAP_1_4.md"
    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    roadmap = parse_roadmap(roadmap_text)
    _validate_roadmap_metadata(roadmap_text, roadmap)

    _expect(roadmap.completed >= 9, "1.4 release-readiness gate requires milestones 1-9 complete")

    project = _project_metadata(root)
    version = str(project["version"])
    requires_python = str(project["requires-python"]).replace(" ", "")
    _expect(
        requires_python == EXPECTED_REQUIRES_PYTHON,
        f"Requires-Python changed unexpectedly: {project['requires-python']!r}",
    )

    _require_files(
        root,
        tuple(f".github/workflows/{name}" for name in REQUIRED_MILESTONE_WORKFLOWS),
        "1.4 milestone workflows",
    )
    _require_files(
        root,
        tuple(f"tools/{name}" for name in REQUIRED_BENCHMARKS),
        "1.4 performance benchmarks",
    )
    _require_files(root, tuple(f"docs/{name}" for name in REQUIRED_DOCS), "1.4 documentation")

    readiness_workflow = root / ".github/workflows/release-readiness-1-4.yml"
    _expect(readiness_workflow.is_file(), "missing 1.4 release-readiness workflow")
    readiness_text = readiness_workflow.read_text(encoding="utf-8")
    for token in (
        "verify_1_4_release_candidate.py",
        "python -m build",
        "python -m twine check",
        "benchmark_multiplayer_2_1_4.py",
        "smoke_renderer2_gl.py",
        "smoke_gpu_particles_gl.py",
        "smoke_scene_acceleration_gl.py",
    ):
        _expect(token in readiness_text, f"1.4 readiness workflow is missing {token!r}")
    _expect("gh-action-pypi-publish" not in readiness_text, "readiness workflow must never publish")
    _expect("gh release create" not in readiness_text, "readiness workflow must never create releases")

    release_workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    release_workflow_has_1_4_gate = (
        "verify_1_4_release_candidate.py --require-complete" in release_workflow
    )
    final_showcase_present = all((root / path).is_file() for path in FINAL_ONLY_FILES)
    status_complete = "STATUS-COMPLETE" in roadmap_text

    if roadmap.completed < EXPECTED_TOTAL:
        _expect(
            version == CURRENT_STABLE_VERSION,
            f"package version must remain {CURRENT_STABLE_VERSION} until 1.4 reaches 10/10",
        )
        _expect(not status_complete, "incomplete 1.4 roadmap must not claim STATUS-COMPLETE")
    else:
        _expect(version == TARGET_VERSION, f"completed 1.4 roadmap requires version {TARGET_VERSION}")

    if require_complete:
        _expect(roadmap.completed == EXPECTED_TOTAL, "1.4 release requires exactly 10/10 milestones")
        _expect(roadmap.percent == 100.0, "1.4 release requires exactly 100.0% roadmap progress")
        _expect(status_complete, "completed 1.4 roadmap must contain STATUS-COMPLETE")
        _expect(final_showcase_present, "final integrated 1.4 showcase and documentation are required")
        _expect(
            release_workflow_has_1_4_gate,
            "release.yml must execute verify_1_4_release_candidate.py --require-complete",
        )
        readme = (root / "README.md").read_text(encoding="utf-8")
        _expect(f"# SwirEngine {TARGET_VERSION}" in readme, "README must identify the 1.4.0 stable release")
        changelog_candidates = tuple((root / "CHANGELOG.d").glob("1.4.0*.md"))
        _expect(bool(changelog_candidates), "1.4.0 release notes are required before publication")

    release_ready = (
        roadmap.completed == EXPECTED_TOTAL
        and roadmap.percent == 100.0
        and status_complete
        and version == TARGET_VERSION
        and final_showcase_present
        and release_workflow_has_1_4_gate
    )
    return ReleaseReadinessReport(
        version=version,
        roadmap=roadmap,
        status_complete=status_complete,
        release_workflow_has_1_4_gate=release_workflow_has_1_4_gate,
        final_showcase_present=final_showcase_present,
        release_ready=release_ready,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the SwirEngine 1.4 release-readiness contract")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="require the final 10/10, 1.4.0 publication contract",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the current checkout)",
    )
    args = parser.parse_args()

    report = audit(args.root, require_complete=args.require_complete)
    state = report.roadmap
    print(
        "SwirEngine 1.4 release readiness: "
        f"{state.completed}/{state.total} ({state.percent:.1f}%), "
        f"version={report.version}, final_showcase={report.final_showcase_present}, "
        f"release_gate={report.release_workflow_has_1_4_gate}, ready={report.release_ready}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
