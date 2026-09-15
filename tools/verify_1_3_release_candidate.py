from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

TARGET_VERSION = "1.3.0"
CURRENT_STABLE_VERSION = "1.2.0"
EXPECTED_TOTAL = 10
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
REQUIRED_1_3_DOCS = (
    "docs/GPU_INSTANCING_1_3.md",
    "docs/SKELETAL_ANIMATION_1_3.md",
    "docs/COLLISION_PHYSICS_1_3.md",
    "docs/NAVIGATION_PATHFINDING_1_3.md",
    "docs/LARGE_WORLD_STREAMING_1_3.md",
    "docs/ADVANCED_SHADER_MATERIAL_1_3.md",
    "docs/RENDERER_2D_POWER_1_3.md",
    "docs/ADVANCED_GAMEPLAY_FRAMEWORK_1_3.md",
    "docs/CREATOR_EDITOR_INTEGRATION_1_3.md",
)
REQUIRED_PUBLIC_SYMBOLS = (
    "Game",
    "InstancedCube3D",
    "ShaderMesh3D",
    "CollisionWorld3D",
)
REQUIRED_NAMESPACES = (
    "src/swirengine/gameplay.py",
    "src/swirengine/navigation.py",
    "src/swirengine/large_world.py",
    "src/swirengine/creator.py",
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
    bar = f"{'█' * filled}{'░' * (20 - filled)} {percent:.1f}%"
    return RoadmapState(completed, remaining, total, percent, bar)


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"required 1.3 release-contract file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def audit(root: Path | None = None, *, require_complete: bool = False) -> AuditReport:
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    checks: list[str] = []
    project = tomllib.loads(_read(root, "pyproject.toml"))["project"]
    version = project["version"]

    _require(
        version in {CURRENT_STABLE_VERSION, TARGET_VERSION},
        f"package version is valid for the 1.3 release phase: {version}",
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

    roadmap_text = _read(root, "ROADMAP_1_3.md")
    roadmap = parse_roadmap(roadmap_text)
    _require("<!-- SWIR-ROADMAP-STANDARD:v1 -->" in roadmap_text, "roadmap standard marker is preserved", checks)
    _require(roadmap.total == EXPECTED_TOTAL, "1.3 roadmap has exactly 10 deliverables", checks)
    _require(roadmap.bar in roadmap_text, "roadmap 20-segment bar matches checkboxes", checks)
    _require(f"ROADMAP-{roadmap.percent:.1f}%25" in roadmap_text, "roadmap badge matches checkboxes", checks)
    _require(f"DONE-{roadmap.completed}%2F{roadmap.total}" in roadmap_text, "roadmap completed badge matches checkboxes", checks)
    _require(
        f"| **{roadmap.completed}** | **{roadmap.remaining}** | **{roadmap.total}** | **{roadmap.percent:.1f}%** |" in roadmap_text,
        "roadmap dashboard table matches checkboxes",
        checks,
    )

    if require_complete:
        _require(roadmap.completed == 10 and roadmap.remaining == 0, "release gate requires exactly 10/10 completed deliverables", checks)
        _require("STATUS-COMPLETE" in roadmap_text, "completed 1.3 roadmap status is COMPLETE", checks)
        _require(version == TARGET_VERSION, f"final package version is {TARGET_VERSION}", checks)
    else:
        _require(roadmap.completed <= 10, "development roadmap cannot exceed 10 deliverables", checks)

    readme = _read(root, "README.md")
    _require("Python 3.10-3.13" in readme, "README documents cross-platform Python support", checks)
    _require("Python 3.14 on Windows" in readme, "README documents verified Windows Python 3.14 scope", checks)
    _require("Neon Frontier 1.3" in readme or roadmap.completed < 10, "README names final Neon Frontier 1.3 validation game", checks)
    if require_complete:
        _require(f"# SwirEngine {TARGET_VERSION}" in readme, "README title matches final 1.3 version", checks)
        _require("current stable release" in readme.lower() and TARGET_VERSION in readme, "README identifies 1.3.0 as stable", checks)

    init_text = _read(root, "src/swirengine/__init__.py")
    for symbol in REQUIRED_PUBLIC_SYMBOLS:
        _require(f'"{symbol}"' in init_text, f"public API exports {symbol}", checks)
    for relative in REQUIRED_NAMESPACES:
        _read(root, relative)
        checks.append(f"1.3 namespace exists: {relative}")
    for relative in REQUIRED_1_3_DOCS:
        _read(root, relative)
        checks.append(f"1.3 creator documentation exists: {relative}")

    frontier = _read(root, "demo_projects/neon_frontier_1_3/run_game.py")
    for token in (
        "InstancedCube3D",
        "ShaderMesh3D",
        "CollisionWorld3D",
        "NavigationGrid3D",
        "LargeWorldStreamer",
        "GameplayRuntime",
        "SWIR_1_3_SMOKE_FRAMES",
        "SWIR_DEMO_RUNTIME_PROBE",
    ):
        _require(token in frontier, f"Neon Frontier exercises {token}", checks)
    _read(root, "demo_projects/neon_frontier_1_3/README.md")

    release = _read(root, ".github/workflows/release.yml")
    _require("verify_1_3_release_candidate.py --require-complete" in release, "release workflow requires complete 1.3 contract", checks)
    _require("pypa/gh-action-pypi-publish@release/v1" in release and "id-token: write" in release, "PyPI publication uses Trusted Publishing", checks)
    _require("skip-existing: true" not in release, "publication cannot hide duplicate artifacts", checks)
    _require("neon_frontier_1_3/run_game.py" in release, "release workflow validates Neon Frontier 1.3", checks)
    _require("python-version: \"3.14\"" in release and "cp314-cp314-win_amd64" in release, "release keeps Windows CPython 3.14 native wheel gate", checks)

    ci = _read(root, ".github/workflows/ci.yml")
    _require("verify_1_3_release_candidate.py" in ci, "normal CI runs the 1.3 release-contract verifier", checks)
    full_game = _read(root, ".github/workflows/full-game-1-3.yml")
    _require("xvfb-run" in full_game, "full-game gate has real OpenGL smoke", checks)
    _require("PyInstaller" in full_game, "full-game gate bundles Windows validation game", checks)

    return AuditReport(version, roadmap, tuple(checks))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the SwirEngine 1.3 final release contract.")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(require_complete=args.require_complete)
    except (AssertionError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"1.3 RELEASE CONTRACT FAILED: {exc}")
        return 1
    print(
        "SwirEngine 1.3 release contract OK: "
        f"version={report.version}, roadmap={report.roadmap.completed}/{report.roadmap.total} "
        f"({report.roadmap.percent:.1f}%), checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
