from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

TARGET_VERSION = "1.2.0"
CURRENT_STABLE_VERSION = "1.1.0"
EXPECTED_TOTAL = 10
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
REQUIRED_1_2_DOCS = (
    "docs/PARTICLES_VFX_1_2.md",
    "docs/TEXT_FONT_PIPELINE_1_2.md",
    "docs/CAMERA_SYSTEMS_1_2.md",
    "docs/SAVE_CONFIG_1_2.md",
    "docs/NETWORK_GAMEPLAY_1_2.md",
    "docs/SCENE_ECS_ERGONOMICS_1_2.md",
    "docs/ASSET_STREAMING_1_2.md",
    "docs/RENDERER_VFX_PERFORMANCE_1_2.md",
    "docs/BUILD_EXPORT_1_2.md",
    "docs/CREATOR_HARDENING_1_2.md",
)
REQUIRED_PUBLIC_API = (
    "Game",
    "Scene",
    "ECSWorld",
    "Prefab",
    "AssetManager",
    "AudioEngine",
    "InputManager",
    "GameplaySession",
    "ProjectExporter",
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
        raise AssertionError(f"required release-contract file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def audit(root: Path | None = None, *, require_complete: bool = False) -> AuditReport:
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    checks: list[str] = []

    pyproject_text = _read(root, "pyproject.toml")
    pyproject = tomllib.loads(pyproject_text)
    project = pyproject["project"]
    version = project["version"]
    _require(
        version in {CURRENT_STABLE_VERSION, TARGET_VERSION},
        f"package version is valid for the 1.2 release phase: {version}",
        checks,
    )
    _require(project["requires-python"] == EXPECTED_PYTHON_RANGE, f"Python contract is {EXPECTED_PYTHON_RANGE}", checks)
    classifiers = set(project.get("classifiers", ()))
    for minor in range(10, 15):
        _require(
            f"Programming Language :: Python :: 3.{minor}" in classifiers,
            f"PyPI classifier includes Python 3.{minor}",
            checks,
        )
    urls = project.get("urls", {})
    _require("ROADMAP_1_2.md" in urls.get("Roadmap", ""), "PyPI Roadmap URL targets active 1.2 roadmap", checks)

    roadmap_text = _read(root, "ROADMAP_1_2.md")
    roadmap = parse_roadmap(roadmap_text)
    _require("<!-- SWIR-ROADMAP-STANDARD:v1 -->" in roadmap_text, "roadmap standard marker is preserved", checks)
    _require(roadmap.total == EXPECTED_TOTAL, "roadmap has exactly 10 deliverables", checks)
    _require(roadmap.bar in roadmap_text, "roadmap 20-segment progress bar matches checkboxes", checks)
    _require(f"ROADMAP-{roadmap.percent:.1f}%25" in roadmap_text, "roadmap badge percentage matches checkboxes", checks)
    _require(f"DONE-{roadmap.completed}%2F{roadmap.total}" in roadmap_text, "roadmap completed badge matches checkboxes", checks)
    _require(
        f"| **{roadmap.completed}** | **{roadmap.remaining}** | **{roadmap.total}** | **{roadmap.percent:.1f}%** |" in roadmap_text,
        "roadmap dashboard table matches checkboxes",
        checks,
    )
    if require_complete:
        _require(roadmap.completed == EXPECTED_TOTAL and roadmap.remaining == 0, "release gate requires exactly 10/10 completed deliverables", checks)
        _require("STATUS-COMPLETE" in roadmap_text, "completed roadmap status badge is COMPLETE", checks)
        _require(version == TARGET_VERSION, f"final package version is {TARGET_VERSION}", checks)

    readme = _read(root, "README.md")
    if require_complete:
        _require(f"# SwirEngine {TARGET_VERSION}" in readme, "README final version matches", checks)
        _require("current stable release" in readme and TARGET_VERSION in readme, "README identifies 1.2 as stable", checks)
    else:
        _require("active 1.2" in readme.lower(), "README identifies active 1.2 development", checks)
    _require("Python 3.10-3.13" in readme, "README documents cross-platform Python support", checks)
    _require("Python 3.14 on Windows" in readme, "README documents verified Python 3.14 scope", checks)
    _require("Neon Cube Hunt 3D" in readme, "README names Neon Cube Hunt 3D", checks)
    _require("Neon Snake 3D" in readme, "README names Neon Snake 3D", checks)

    init_text = _read(root, "src/swirengine/__init__.py")
    for symbol in REQUIRED_PUBLIC_API:
        _require(f'"{symbol}"' in init_text, f"public API exports {symbol}", checks)

    for relative in REQUIRED_1_2_DOCS:
        _read(root, relative)
        checks.append(f"creator documentation exists: {relative}")

    ci = _read(root, ".github/workflows/ci.yml")
    release = _read(root, ".github/workflows/release.yml")
    cube = _read(root, ".github/workflows/demo-game3d.yml")
    snake = _read(root, ".github/workflows/neon-snake-3d.yml")
    desktop_export = _read(root, ".github/workflows/desktop-export.yml")

    _require("python tools/verify_1_2_release_candidate.py" in ci, "normal CI runs the 1.2 release-contract verifier", checks)
    _require(
        "python tools/verify_1_2_release_candidate.py --require-complete" in release,
        "publication workflow requires the complete 1.2 release contract",
        checks,
    )
    _require("verify_1_1_release_candidate.py" not in release, "publication workflow no longer gates on 1.1", checks)
    _require("swirengine==1.1.0" not in release, "publication workflow has no stale 1.1 wheel pin", checks)
    _require(
        "pypa/gh-action-pypi-publish@release/v1" in release and "id-token: write" in release,
        "PyPI publication uses Trusted Publishing",
        checks,
    )
    _require("skip-existing: true" not in release, "final 1.2 publication fails on duplicate artifacts instead of hiding them", checks)
    _require("tools/benchmark_static_3d_batch.py" in ci and "--assert-win" in ci, "CI retains static 3D performance gate", checks)
    _require("tools/benchmark_asset_preload.py" in ci, "CI retains async asset preload performance gate", checks)

    for workflow_name, workflow in (("Neon Cube Hunt 3D", cube), ("Neon Snake 3D", snake)):
        _require("xvfb-run" in workflow, f"{workflow_name} has a real OpenGL smoke test", checks)
        _require("PyInstaller" in workflow, f"{workflow_name} is bundled on desktop CI", checks)
        _require("SWIR_DEMO_RUNTIME_PROBE" in workflow, f"{workflow_name} probes packaged Windows runtime", checks)
        _require("gh release" not in workflow, f"{workflow_name} cannot bypass release freeze", checks)

    for runner in ("windows-latest", "ubuntu-latest", "macos-latest"):
        _require(runner in desktop_export, f"desktop export gate includes {runner}", checks)
    _require(
        "verify_desktop_export.py" in desktop_export and "--onedir" in desktop_export,
        "desktop export gate covers default one-file and explicit one-directory builds",
        checks,
    )

    project_contracts = {
        "neon_cube_hunt_3d": ("README.md", "pyproject.toml", "run_game.py"),
        "neon_snake_3d": ("README.md", "PROJECT.md", ".release-version", "run_game.py"),
    }
    for project_name, required_entries in project_contracts.items():
        project_root = root / "demo_projects" / project_name
        for required in required_entries:
            _require((project_root / required).exists(), f"sample project {project_name} contains {required}", checks)

    if require_complete:
        changelog = _read(root, "CHANGELOG.md")
        _require("## 1.2.0" in changelog, "CHANGELOG contains final 1.2.0 release section", checks)

    return AuditReport(version=version, roadmap=roadmap, checks=tuple(checks))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the SwirEngine 1.2 creator/release contract.")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="require ROADMAP_1_2.md at exactly 10/10 and package version 1.2.0",
    )
    args = parser.parse_args()

    try:
        report = audit(require_complete=args.require_complete)
    except (AssertionError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"RELEASE CONTRACT FAILED: {exc}")
        return 1

    print(
        "SwirEngine 1.2 release contract OK: "
        f"version={report.version}, roadmap={report.roadmap.completed}/{report.roadmap.total} "
        f"({report.roadmap.percent:.1f}%), checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
