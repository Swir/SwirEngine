from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

EXPECTED_VERSION = "1.1.0"
EXPECTED_TOTAL = 10
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"


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

    pyproject = _read(root, "pyproject.toml")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    if match is None:
        raise AssertionError("pyproject.toml has no project version")
    version = match.group(1)
    _require(version == EXPECTED_VERSION, f"target version is {EXPECTED_VERSION}", checks)
    _require(
        f'requires-python = "{EXPECTED_PYTHON_RANGE}"' in pyproject,
        f"Python contract is {EXPECTED_PYTHON_RANGE}",
        checks,
    )
    for minor in range(10, 15):
        _require(
            f'Programming Language :: Python :: 3.{minor}' in pyproject,
            f"PyPI classifier includes Python 3.{minor}",
            checks,
        )

    roadmap_text = _read(root, "ROADMAP_1_1.md")
    roadmap = parse_roadmap(roadmap_text)
    _require(
        "<!-- SWIR-ROADMAP-STANDARD:v1 -->" in roadmap_text,
        "roadmap standard marker is preserved",
        checks,
    )
    _require(roadmap.total == EXPECTED_TOTAL, "roadmap has exactly 10 deliverables", checks)
    _require(roadmap.bar in roadmap_text, "roadmap 20-segment progress bar matches checkboxes", checks)
    _require(
        f"ROADMAP-{roadmap.percent:.1f}%25" in roadmap_text,
        "roadmap badge percentage matches checkboxes",
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
        "roadmap dashboard table matches checkboxes",
        checks,
    )
    if require_complete:
        _require(
            roadmap.completed == EXPECTED_TOTAL and roadmap.remaining == 0,
            "release gate requires exactly 10/10 completed deliverables",
            checks,
        )

    readme = _read(root, "README.md")
    _require(f"# SwirEngine {EXPECTED_VERSION}" in readme, "README target version matches", checks)
    _require("Python 3.10-3.13" in readme, "README documents cross-platform Python support", checks)
    _require("Python 3.14 on Windows" in readme, "README documents verified Python 3.14 scope", checks)
    _require("10/10 = 100%" in readme, "README documents the release freeze", checks)
    _require("Neon Cube Hunt 3D" in readme, "README names the complete 3D sample game", checks)
    _require("Neon Snake 3D" in readme, "README names the second runtime demo", checks)

    ci = _read(root, ".github/workflows/ci.yml")
    release = _read(root, ".github/workflows/release.yml")
    cube = _read(root, ".github/workflows/demo-game3d.yml")
    snake = _read(root, ".github/workflows/neon-snake-3d.yml")

    _require(
        "python tools/verify_1_1_release_candidate.py" in ci,
        "normal CI runs the 1.1 release-contract verifier",
        checks,
    )
    _require(
        "python tools/verify_1_1_release_candidate.py --require-complete" in release,
        "publication workflow re-runs the complete release contract",
        checks,
    )
    _require(
        "pypa/gh-action-pypi-publish@release/v1" in release and "id-token: write" in release,
        "PyPI publication uses Trusted Publishing",
        checks,
    )
    _require(
        "tools/benchmark_static_3d_batch.py" in ci and "--assert-win" in ci,
        "CI retains the static 3D performance regression gate",
        checks,
    )
    _require(
        "tools/benchmark_asset_preload.py" in ci,
        "CI retains the async asset preload performance regression gate",
        checks,
    )

    for workflow_name, workflow in (("Neon Cube Hunt 3D", cube), ("Neon Snake 3D", snake)):
        _require("xvfb-run" in workflow, f"{workflow_name} has a real OpenGL smoke test", checks)
        _require("PyInstaller" in workflow, f"{workflow_name} is bundled on desktop CI", checks)
        _require(
            "SWIR_DEMO_RUNTIME_PROBE" in workflow,
            f"{workflow_name} probes the packaged Windows runtime",
            checks,
        )
        _require("gh release" not in workflow, f"{workflow_name} cannot bypass the release freeze", checks)
        _require("contents: write" not in workflow, f"{workflow_name} workflow has no release write permission", checks)

    project_contracts = {
        "neon_cube_hunt_3d": ("README.md", "pyproject.toml", "run_game.py", "neon_cube_hunt"),
        "neon_snake_3d": ("README.md", "PROJECT.md", ".release-version", "run_game.py", "neon_snake"),
    }
    for project, required_entries in project_contracts.items():
        project_root = root / "demo_projects" / project
        for required in required_entries:
            _require(
                (project_root / required).exists(),
                f"sample project {project} contains {required}",
                checks,
            )

    return AuditReport(version=version, roadmap=roadmap, checks=tuple(checks))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the SwirEngine 1.1 release contract.")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless ROADMAP_1_1.md is exactly 10/10 = 100%",
    )
    args = parser.parse_args()

    try:
        report = audit(require_complete=args.require_complete)
    except AssertionError as exc:
        print(f"RELEASE CONTRACT FAILED: {exc}")
        return 1

    print(
        "SwirEngine release contract OK: "
        f"version={report.version}, roadmap={report.roadmap.completed}/{report.roadmap.total} "
        f"({report.roadmap.percent:.1f}%), checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
