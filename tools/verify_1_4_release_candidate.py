from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

TARGET_VERSION = "1.4.0"
PREVIOUS_STABLE_VERSION = "1.3.0"
ACTIVE_STABLE_VERSIONS = {PREVIOUS_STABLE_VERSION, TARGET_VERSION, "1.5.0"}
EXPECTED_TOTAL = 10
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
REQUIRED_1_4_DOCS = (
    "docs/TERRAIN_WORLD_LOD_1_4.md",
    "docs/PHYSICS_2_1_4.md",
    "docs/CHARACTER_CONTROLLERS_1_4.md",
    "docs/RENDERER2_1_4.md",
    "docs/GPU_VFX_PARTICLES_1_4.md",
    "docs/SCENE_ACCELERATION_OCCLUSION_1_4.md",
    "docs/ASSET_PIPELINE_2_1_4.md",
    "docs/EDITOR_AUTHORING_1_4.md",
    "docs/MULTIPLAYER_2_1_4.md",
    "docs/RELEASE_HARDENING_1_4.md",
)


@dataclass(frozen=True, slots=True)
class RoadmapState:
    completed: int
    remaining: int
    total: int
    percent: float
    bar: str


@dataclass(frozen=True, slots=True)
class AuditReport:
    version: str
    roadmap: RoadmapState
    checks: tuple[str, ...]


def parse_roadmap(text: str) -> RoadmapState:
    completed = len(re.findall(r"^- \[x\] ", text, flags=re.MULTILINE | re.IGNORECASE))
    remaining = len(re.findall(r"^- \[ \] ", text, flags=re.MULTILINE))
    total = completed + remaining
    percent = 0.0 if total == 0 else completed / total * 100.0
    filled = 0 if total == 0 else round(completed / total * 20)
    return RoadmapState(
        completed=completed,
        remaining=remaining,
        total=total,
        percent=percent,
        bar=f"{'█' * filled}{'░' * (20 - filled)} {percent:.1f}%",
    )


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"required 1.4 release-contract file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def audit(root: Path | None = None, *, require_complete: bool = False) -> AuditReport:
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    checks: list[str] = []

    project = tomllib.loads(_read(root, "pyproject.toml"))["project"]
    version = str(project["version"])
    _require(
        version in ACTIVE_STABLE_VERSIONS,
        f"package version preserves the locked 1.4 compatibility line: {version}",
        checks,
    )
    _require(
        project["requires-python"] == EXPECTED_PYTHON_RANGE,
        f"Python contract is {EXPECTED_PYTHON_RANGE}",
        checks,
    )
    classifiers = set(project.get("classifiers", ()))
    for minor in range(10, 15):
        _require(
            f"Programming Language :: Python :: 3.{minor}" in classifiers,
            f"PyPI classifier includes Python 3.{minor}",
            checks,
        )
    urls = project.get("urls", {})
    if version == TARGET_VERSION:
        _require(
            str(urls.get("Roadmap", "")).endswith("/ROADMAP_1_4.md"),
            "1.4 publication metadata points at the 1.4 roadmap",
            checks,
        )
    else:
        _require(
            str(urls.get("1.4 Roadmap", "")).endswith("/ROADMAP_1_4.md"),
            "later stable metadata preserves the locked 1.4 roadmap link",
            checks,
        )

    roadmap_text = _read(root, "ROADMAP_1_4.md")
    roadmap = parse_roadmap(roadmap_text)
    _require(
        "<!-- SWIR-ROADMAP-STANDARD:v1 -->" in roadmap_text,
        "roadmap standard marker is preserved",
        checks,
    )
    _require(roadmap.total == EXPECTED_TOTAL, "1.4 roadmap has exactly 10 deliverables", checks)
    _require(roadmap.bar in roadmap_text, "roadmap 20-segment bar matches checkboxes", checks)
    _require(
        f"ROADMAP-{roadmap.percent:.1f}%25" in roadmap_text,
        "roadmap badge matches checkboxes",
        checks,
    )
    _require(
        f"DONE-{roadmap.completed}%2F{roadmap.total}" in roadmap_text,
        "roadmap completed badge matches checkboxes",
        checks,
    )
    _require(
        f"| **{roadmap.completed}** | **{roadmap.remaining}** | **{roadmap.total}** | **{roadmap.percent:.1f}%** |"
        in roadmap_text,
        "roadmap dashboard matches checkboxes",
        checks,
    )

    if require_complete:
        _require(
            roadmap.completed == 10 and roadmap.remaining == 0,
            "locked 1.4 contract requires exactly 10/10 deliverables",
            checks,
        )
        _require(
            "STATUS-COMPLETE" in roadmap_text,
            "completed 1.4 roadmap status is COMPLETE",
            checks,
        )
        _require(
            version in {TARGET_VERSION, "1.5.0"},
            "complete 1.4 compatibility contract permits the 1.4 publication or later 1.5 stable line",
            checks,
        )
    else:
        _require(
            roadmap.completed in {9, 10},
            "1.4 hardening/compatibility phase must be at milestone 9 or 10",
            checks,
        )
        if roadmap.completed < 10:
            _require(
                version == PREVIOUS_STABLE_VERSION,
                "stable package remains 1.3.0 before 1.4 reaches 10/10",
                checks,
            )

    init_text = _read(root, "src/swirengine/__init__.py")
    _require(
        f'__version__ = "{version}"' in init_text,
        "runtime __version__ matches current project metadata",
        checks,
    )

    for relative in REQUIRED_1_4_DOCS:
        _read(root, relative)
        checks.append(f"1.4 documentation exists: {relative}")

    demo = _read(root, "demo_projects/neon_frontier_1_4/run_game.py")
    for token in (
        "HeightmapTerrain",
        "PhysicsScene3D",
        "CharacterController3D",
        "configure_renderer2",
        "gpu_particles",
        "LargeWorldStreamer",
        "EditorAuthoringWorkspace",
        "SnapshotDelta",
        "SWIR_1_4_SMOKE_FRAMES",
        "SWIR_DEMO_RUNTIME_PROBE",
    ):
        _require(token in demo, f"Neon Frontier 1.4 exercises {token}", checks)
    _read(root, "demo_projects/neon_frontier_1_4/README.md")

    hardening = _read(root, ".github/workflows/showcase-hardening-1-4.yml")
    for token in (
        "verify_1_4_release_candidate.py",
        "benchmark_showcase_1_4.py",
        "xvfb-run",
        "SWIR_1_4_SMOKE_FRAMES",
        "PyInstaller",
        "NeonFrontier14",
        "SWIR_DEMO_RUNTIME_PROBE",
    ):
        _require(token in hardening, f"1.4 hardening workflow includes {token}", checks)
    if require_complete:
        _require(
            "verify_1_4_release_candidate.py --require-complete" in hardening,
            "locked 1.4 hardening workflow keeps the complete compatibility contract",
            checks,
        )

    release = _read(root, ".github/workflows/release.yml")
    _require(
        "pypa/gh-action-pypi-publish@release/v1" in release,
        "current publication workflow uses Trusted Publishing",
        checks,
    )
    _require("id-token: write" in release, "release workflow keeps OIDC publication permission", checks)
    _require(
        "skip-existing: true" not in release,
        "publication cannot hide duplicate artifacts",
        checks,
    )
    if require_complete and version == TARGET_VERSION:
        _require(
            "verify_1_4_release_candidate.py --require-complete" in release,
            "historical 1.4 publication workflow hard-gates the complete 1.4 contract",
            checks,
        )
        _require(
            "neon_frontier_1_4/run_game.py" in release,
            "historical 1.4 publication workflow validates Neon Frontier 1.4",
            checks,
        )
        _require(
            "RELEASE_NOTES_1_4.md" in release,
            "historical GitHub release is wired to the 1.4 release notes",
            checks,
        )
    _require(
        "branches:" not in release.split("jobs:", 1)[0],
        "publication workflow has no main-branch publish trigger",
        checks,
    )

    ci = _read(root, ".github/workflows/ci.yml")
    _require(
        "verify_1_3_release_candidate.py" in ci,
        "historical 1.3 compatibility contract remains protected",
        checks,
    )
    _require(
        "verify_1_4_release_candidate.py" in ci,
        "normal CI audits the locked 1.4 compatibility contract",
        checks,
    )

    readme = _read(root, "README.md")
    _require("Neon Frontier 1.4" in readme, "README keeps the locked 1.4 showcase documented", checks)
    if require_complete:
        _require("10/10 = 100.0%" in readme, "README reports a verified complete stable roadmap", checks)
        if version == TARGET_VERSION:
            _require(
                f"# SwirEngine {TARGET_VERSION}" in readme,
                "README title matches the historical 1.4 publication",
                checks,
            )
        else:
            _require(
                "SwirEngine 1.4" in readme and "released and locked" in readme,
                "later README preserves 1.4 as a released and locked compatibility line",
                checks,
            )
        notes = _read(root, "RELEASE_NOTES_1_4.md")
        _require(TARGET_VERSION in notes, "locked 1.4 release notes still name version 1.4.0", checks)

    return AuditReport(version=version, roadmap=roadmap, checks=tuple(checks))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the locked SwirEngine 1.4 release/compatibility contract."
    )
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(require_complete=args.require_complete)
    except (AssertionError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"1.4 RELEASE CONTRACT FAILED: {exc}")
        return 1
    print(
        "SwirEngine 1.4 release contract OK: "
        f"version={report.version}, roadmap={report.roadmap.completed}/{report.roadmap.total} "
        f"({report.roadmap.percent:.1f}%), checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
