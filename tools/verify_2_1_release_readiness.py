from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

EXPECTED_STABLE_VERSION = "2.0.0"
EXPECTED_CANDIDATE_VERSION = "2.1.0"
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
EXPECTED_COMPLETED = 10
EXPECTED_TOTAL = 10
ACCEPTED_PREFLIGHT_HEAD = "7b7cecb02b0d573d72cc55ec34ecfd307492f3ff"
ASCII_BAR_WIDTH = 30
PYPI_PROGRESS_START = "<!-- SWIR-PYPI-PROGRESS:START -->"
PYPI_PROGRESS_END = "<!-- SWIR-PYPI-PROGRESS:END -->"
PYPI_BLOCK_RE = re.compile(
    rf"{re.escape(PYPI_PROGRESS_START)}.*?{re.escape(PYPI_PROGRESS_END)}",
    re.DOTALL,
)
MILESTONE_RE = re.compile(
    r"^- \[(?P<state>[ xX])\] \*\*(?P<number>\d+)\.",
    re.MULTILINE,
)
SUMMARY_RE = re.compile(
    r"Current verified progress:\s*(?P<done>\d+)/(?P<total>\d+)\s+milestones\s*=\s*"
    r"(?P<percent>\d+(?:\.\d+)?)%\."
)
M10_CLOSED_RE = re.compile(
    r"^- \[[xX]\] \*\*10\. Real-game editor gate and 2\.1 release readiness\.\*\*",
    re.MULTILINE,
)

REQUIRED_DOCS = (
    "docs/API_STABILITY.md",
    "docs/MIGRATING_TO_2_0.md",
    "docs/MIGRATING_TO_2_1.md",
    "docs/SUPPORT_MATRIX_2_0.md",
    "docs/PACKAGING_SHIPPING_2_0.md",
    "docs/PERFORMANCE_EVIDENCE_2_0.md",
    "docs/RELEASE_SAFETY_2_0.md",
    "docs/RELEASE_GATE_2_1.md",
)
REQUIRED_VERIFIERS = (
    "tools/generate_progress_svg.py",
    "tools/verify_editor_real_game_gate_2_1.py",
    "tools/verify_platform_matrix_2_0.py",
    "tools/verify_clean_wheel_2_0.py",
    "tools/verify_packaging_shipping_2_0.py",
    "tools/verify_performance_evidence_2_0.py",
    "tools/verify_release_safety_2_0.py",
    "tools/verify_2_1_release_readiness.py",
)
REQUIRED_FIXTURES = (
    "examples/2d_game_demo/run_game.py",
    "examples/3d_game_demo/run_game.py",
    "examples/multiplayer_game_demo/run_game.py",
)
REQUIRED_WORKFLOWS = (
    ".github/workflows/editor-real-game-milestone-10.yml",
    ".github/workflows/platform-matrix-2.0.yml",
    ".github/workflows/packaging-shipping-2.0.yml",
    ".github/workflows/performance-evidence-2.0.yml",
    ".github/workflows/editor-release-readiness-milestone-10.yml",
)


@dataclass(frozen=True, slots=True)
class RoadmapState:
    completed: int
    total: int
    percent: float


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    version: str
    roadmap: RoadmapState
    checks: tuple[str, ...]


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"required 2.1 readiness file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def parse_roadmap(text: str) -> RoadmapState:
    matches = list(MILESTONE_RE.finditer(text))
    numbers = [int(match.group("number")) for match in matches]
    if not matches or numbers != list(range(1, len(matches) + 1)):
        raise AssertionError("2.1 roadmap milestone numbering must be contiguous from 1")
    completed = sum(match.group("state").lower() == "x" for match in matches)
    total = len(matches)
    percent = completed / total * 100.0
    summary = SUMMARY_RE.search(text)
    if summary is None:
        raise AssertionError("2.1 roadmap is missing the verified progress summary")
    if int(summary.group("done")) != completed or int(summary.group("total")) != total:
        raise AssertionError("2.1 roadmap summary disagrees with the milestone checklist")
    if abs(float(summary.group("percent")) - percent) > 0.05:
        raise AssertionError("2.1 roadmap percentage disagrees with the milestone checklist")
    return RoadmapState(completed=completed, total=total, percent=percent)


def require_accepted_roadmap(text: str, state: RoadmapState) -> None:
    if state.completed != EXPECTED_COMPLETED or state.total != EXPECTED_TOTAL:
        raise AssertionError("2.1 milestone acceptance requires exactly 10/10 verified milestones")
    if len(M10_CLOSED_RE.findall(text)) != 1:
        raise AssertionError("Milestone 10 must be accepted exactly once in the final 2.1 roadmap")
    if ACCEPTED_PREFLIGHT_HEAD not in text:
        raise AssertionError("Milestone 10 acceptance must cite the exact green Phase A preflight head")


def expected_pypi_progress(state: RoadmapState) -> str:
    filled = state.completed * ASCII_BAR_WIDTH // state.total
    if state.completed < state.total:
        filled = min(ASCII_BAR_WIDTH - 1, filled)
    status = "COMPLETE" if state.completed >= state.total else "IN PROGRESS"
    bar = "#" * filled + "-" * (ASCII_BAR_WIDTH - filled)
    return (
        f"{PYPI_PROGRESS_START}\n"
        "```text\n"
        "Scope: SwirEngine 2.1 - SwirEditor & Creator Workflow\n"
        f"Progress: [{bar}] {state.percent:.1f}%\n"
        f"Counter: {state.completed} / {state.total} milestones\n"
        f"Status: {status}\n"
        "```\n"
        f"{PYPI_PROGRESS_END}"
    )


def validate_pypi_progress(readme: str, state: RoadmapState) -> None:
    if readme.count(PYPI_PROGRESS_START) != 1 or readme.count(PYPI_PROGRESS_END) != 1:
        raise AssertionError("README must keep exactly one SWIR-PYPI-PROGRESS block")
    match = PYPI_BLOCK_RE.search(readme)
    if match is None or match.group(0) != expected_pypi_progress(state):
        raise AssertionError("README PyPI progress block must exactly match ROADMAP_2_1.md")
    block = match.group(0)
    if not block.isascii() or "<img" in block or ".svg" in block:
        raise AssertionError("README PyPI progress block must be deterministic plain ASCII")


def audit(root: Path | None = None) -> ReadinessReport:
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    checks: list[str] = []

    project = tomllib.loads(_read(root, "pyproject.toml"))["project"]
    version = str(project["version"])
    _require(
        version in {EXPECTED_STABLE_VERSION, EXPECTED_CANDIDATE_VERSION},
        "2.1 source readiness permits only published stable 2.0.0 or guarded candidate 2.1.0 metadata",
        checks,
    )
    init_text = _read(root, "src/swirengine/__init__.py")
    _require(
        f'__version__ = "{version}"' in init_text,
        "runtime __version__ matches current source package metadata",
        checks,
    )
    _require(
        project["requires-python"] == EXPECTED_PYTHON_RANGE,
        f"Python contract remains {EXPECTED_PYTHON_RANGE}",
        checks,
    )
    classifiers = set(project.get("classifiers", ()))
    for minor in range(10, 15):
        _require(
            f"Programming Language :: Python :: 3.{minor}" in classifiers,
            f"PyPI classifier includes Python 3.{minor}",
            checks,
        )

    roadmap_text = _read(root, "ROADMAP_2_1.md")
    state = parse_roadmap(roadmap_text)
    require_accepted_roadmap(roadmap_text, state)
    checks.append("2.1 roadmap has exact green Phase A evidence and 10/10 milestone acceptance")

    readme = _read(root, "README.md")
    notes = _read(root, "RELEASE_NOTES_2_1.md")
    validate_pypi_progress(readme, state)
    checks.append("README PyPI ASCII progress matches the authoritative 2.1 roadmap")

    publication_final = (
        version == EXPECTED_CANDIDATE_VERSION
        and "**Latest public stable release:** **SwirEngine 2.1.0**" in readme
        and notes.startswith("# SwirEngine 2.1.0 Release Notes")
        and "NOT PUBLISHED" not in notes
    )
    if publication_final:
        _require(
            "**2.1 release:** **PUBLISHED — GitHub Release and PyPI verified**" in readme,
            "README final publication state identifies the verified 2.1 release",
            checks,
        )
    else:
        _require(
            "**Latest public stable release:** **SwirEngine 2.0.0**" in readme,
            "README keeps 2.0.0 as latest stable before 2.1 publication",
            checks,
        )
        _require(
            "SwirEngine 2.1 roadmap acceptance is complete, but publication remains a separate guarded decision"
            in readme,
            "README separates 2.1 roadmap completion from public release before publication",
            checks,
        )
        if version == EXPECTED_CANDIDATE_VERSION:
            _require(
                "NOT PUBLISHED" in notes,
                "2.1 candidate metadata remains explicitly non-published before Phase C publication",
                checks,
            )

    urls = project.get("urls", {})
    expected_roadmap = "ROADMAP_2_1.md" if publication_final else "ROADMAP_2_0.md"
    _require(
        str(urls.get("Roadmap", "")).endswith(expected_roadmap),
        "primary package roadmap matches the current publication phase",
        checks,
    )
    _require(
        str(urls.get("2.1 Roadmap", "")).endswith("ROADMAP_2_1.md"),
        "package metadata exposes the completed 2.1 source roadmap",
        checks,
    )

    for relative in REQUIRED_DOCS + REQUIRED_VERIFIERS + REQUIRED_FIXTURES + REQUIRED_WORKFLOWS:
        _read(root, relative)
    checks.append("M10 docs, verifiers, fixtures and CI surfaces are present")

    migration = _read(root, "docs/MIGRATING_TO_2_1.md")
    _require(
        "2.0.0" in migration and "source development" in migration.lower(),
        "2.1 migration guidance distinguishes stable 2.0.0 from source development",
        checks,
    )
    gate = _read(root, "docs/RELEASE_GATE_2_1.md")
    _require(
        ACCEPTED_PREFLIGHT_HEAD in gate and "10/10 = 100.0%" in gate,
        "2.1 release gate records the accepted preflight head and Phase B milestone target",
        checks,
    )
    _require(
        "Publication is a separate guarded decision" in gate,
        "2.1 release gate keeps publication separate from milestone acceptance",
        checks,
    )

    return ReadinessReport(version=version, roadmap=state, checks=tuple(checks))


def main() -> int:
    report = audit()
    print(
        "SwirEngine 2.1 milestone acceptance OK: "
        f"source-version={report.version}, roadmap={report.roadmap.completed}/{report.roadmap.total}, "
        f"progress={report.roadmap.percent:.1f}%, checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
