from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - CPython 3.10
    import tomli as tomllib

PUBLIC_STABLE_VERSION = "2.1.0"
EXPECTED_CANDIDATE_VERSION = "2.2.0"
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
EXPECTED_COMPLETED = 9
EXPECTED_TOTAL = 10
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
M10_OPEN_RE = re.compile(
    r"^- \[ \] \*\*10\. Production acceptance and 2\.2 release readiness\.\*\*",
    re.MULTILINE,
)

REQUIRED_DOCS = (
    "docs/API_STABILITY.md",
    "docs/MIGRATING_TO_2_1.md",
    "docs/MIGRATING_TO_2_2.md",
    "docs/SUPPORT_MATRIX_2_0.md",
    "docs/PACKAGING_SHIPPING_2_0.md",
    "docs/PERFORMANCE_EVIDENCE_2_0.md",
    "docs/RELEASE_SAFETY_2_0.md",
    "docs/RELEASE_GATE_2_1.md",
    "docs/RELEASE_GATE_2_2.md",
)
REQUIRED_VERIFIERS = (
    "tools/generate_progress_svg.py",
    "tools/verify_editor_real_game_gate_2_1.py",
    "tools/verify_platform_matrix_2_0.py",
    "tools/verify_clean_wheel_2_0.py",
    "tools/verify_packaging_shipping_2_0.py",
    "tools/verify_performance_evidence_2_0.py",
    "tools/verify_release_safety_2_0.py",
    "tools/verify_distribution_audit_data_2_2.py",
    "tools/verify_required_workflows_2_2.py",
    "tools/verify_candidate_merge_2_2.py",
    "tools/verify_publication_chain_2_2.py",
    "tools/verify_sdist_identity_2_2.py",
    "tools/release_evidence_2_2.py",
    "tools/reconcile_release_2_2.py",
    "tools/verify_2_2_release_readiness.py",
)
REQUIRED_FIXTURES = (
    "examples/2d_game_demo/run_game.py",
    "examples/3d_game_demo/run_game.py",
    "examples/multiplayer_game_demo/run_game.py",
)
REQUIRED_WORKFLOWS = (
    ".github/workflows/editor-real-game-milestone-10.yml",
    ".github/workflows/publication-gate-2.2.yml",
    ".github/workflows/release.yml",
)
PHASE_A_WORKFLOW = ".github/workflows/release-readiness-2.2.yml"
PHASE_B_WORKFLOW = ".github/workflows/release-candidate-2.2.yml"
PHASE_B_FILES = (
    "PYPI_DESCRIPTION_2_2.md",
    "RELEASE_NOTES_2_2.md",
    "tools/candidate_evidence_2_2.py",
    "tools/verify_2_2_release_candidate.py",
    PHASE_B_WORKFLOW,
)
FORBIDDEN_WORKFLOW_FRAGMENTS = (
    "contents: write",
    "id-token: write",
    "packages: write",
    "pull-requests: write",
    "pypa/gh-action-pypi-publish",
    "gh release create",
    "git push",
    "git tag",
    "twine upload",
)


@dataclass(frozen=True, slots=True)
class RoadmapState:
    completed: int
    total: int
    percent: float


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    phase: str
    version: str
    roadmap: RoadmapState
    checks: tuple[str, ...]


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"required 2.2 readiness file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def parse_roadmap(text: str) -> RoadmapState:
    matches = list(MILESTONE_RE.finditer(text))
    numbers = [int(match.group("number")) for match in matches]
    if numbers != list(range(1, EXPECTED_TOTAL + 1)):
        raise AssertionError("2.2 roadmap must contain exactly ten contiguous milestones")
    completed = sum(match.group("state").lower() == "x" for match in matches)
    total = len(matches)
    percent = completed / total * 100.0
    summary = SUMMARY_RE.search(text)
    if summary is None:
        raise AssertionError("2.2 roadmap is missing the verified progress summary")
    if int(summary.group("done")) != completed or int(summary.group("total")) != total:
        raise AssertionError("2.2 roadmap summary disagrees with the milestone checklist")
    if abs(float(summary.group("percent")) - percent) > 0.05:
        raise AssertionError("2.2 roadmap percentage disagrees with the milestone checklist")
    return RoadmapState(completed=completed, total=total, percent=percent)


def require_phase_a_roadmap(text: str, state: RoadmapState) -> None:
    if state.completed != EXPECTED_COMPLETED or state.total != EXPECTED_TOTAL:
        raise AssertionError("2.2 Phase A must remain exactly 9/10 until final Phase E acceptance")
    if len(M10_OPEN_RE.findall(text)) != 1:
        raise AssertionError("Milestone 10 must remain open exactly once during 2.2 Phase A")


def _expected_readme_progress(root: Path) -> str:
    try:
        from tools.generate_progress_svg import parse_progress, render_readme_progress
    except ImportError:  # pragma: no cover - direct script execution
        from generate_progress_svg import parse_progress, render_readme_progress

    roadmap = _read(root, "ROADMAP_2_2.md")
    return render_readme_progress(parse_progress(roadmap, source="ROADMAP_2_2.md"))


def validate_readme(
    readme: str,
    state: RoadmapState,
    *,
    root: Path,
    phase: str | None = None,
) -> None:
    if readme.count(PYPI_PROGRESS_START) != 1 or readme.count(PYPI_PROGRESS_END) != 1:
        raise AssertionError("README must keep exactly one SWIR-PYPI-PROGRESS block")
    match = PYPI_BLOCK_RE.search(readme)
    if match is None or match.group(0) != _expected_readme_progress(root):
        raise AssertionError("README PyPI progress must exactly match ROADMAP_2_2.md")
    if not match.group(0).isascii() or "<img" in match.group(0) or ".svg" in match.group(0):
        raise AssertionError("README PyPI progress block must remain deterministic plain ASCII")
    if state.completed != EXPECTED_COMPLETED or state.total != EXPECTED_TOTAL:
        raise AssertionError("README pre-release validation requires the frozen 9/10 roadmap state")
    common_required = (
        "**Latest public stable release:** **SwirEngine 2.1.0**",
        "**2.2 roadmap:** **9/10 milestones = 90.0% - IN PROGRESS**",
        '"swirengine==2.1.0"',
        '"swirengine[audio]==2.1.0"',
    )
    for fragment in common_required:
        if fragment not in readme:
            raise AssertionError(f"README pre-release contract is missing: {fragment}")

    normalized = " ".join(readme.split()).casefold()
    if phase is None:
        phase = "B" if "bound non-publishing candidate" in normalized else "A"
    if phase == "A":
        if "swirengine 2.2 is source development only" not in normalized:
            raise AssertionError("README Phase A source-development boundary is missing")
    elif phase == "B":
        for fragment in ("swirengine 2.2.0", "bound non-publishing candidate"):
            if fragment not in normalized:
                raise AssertionError(f"README Phase B contract is missing: {fragment}")
    else:
        raise AssertionError(f"unsupported 2.2 pre-release phase: {phase}")
    if '"swirengine==2.2.0"' in readme or '"swirengine[audio]==2.2.0"' in readme:
        raise AssertionError("README must not advertise a public 2.2.0 install before Phase E")


def validate_non_publishing_workflow(workflow: str, *, phase: str | None = None) -> None:
    folded = workflow.casefold()
    if not re.search(r"(?m)^permissions:\s*\n\s+contents:\s+read\s*$", workflow):
        raise AssertionError("2.2 pre-release workflow must declare top-level contents: read")
    for fragment in FORBIDDEN_WORKFLOW_FRAGMENTS:
        if fragment in folded:
            raise AssertionError(
                f"2.2 pre-release workflow contains forbidden publishing capability: {fragment}"
            )
    if phase is None:
        phase = "B" if "release/2.2.0-candidate" in workflow else "A"
    common = (
        "persist-credentials: false",
        "python tools/verify_required_workflows_2_2.py",
        "python tools/verify_2_2_release_readiness.py",
        "python tools/verify_distribution_audit_data_2_2.py",
        "python -m build",
    )
    if phase == "A":
        required = common + (
            "github.event.pull_request.head.sha || github.sha",
            "--expected-version 2.1.0",
        )
    elif phase == "B":
        required = common + (
            "github.event.pull_request.head.sha",
            "github.event.pull_request.head.repo.full_name",
            "github.event.pull_request.head.ref",
            "github.event.pull_request.base.ref",
            "Swir/SwirEngine",
            "release/2.2.0-candidate",
            "python tools/verify_2_2_release_candidate.py",
            "python tools/candidate_evidence_2_2.py generate",
            "python tools/candidate_evidence_2_2.py verify",
            "--expected-version 2.2.0",
        )
    else:
        raise AssertionError(f"unsupported 2.2 pre-release phase: {phase}")
    for fragment in required:
        if fragment not in workflow:
            raise AssertionError(f"2.2 pre-release workflow is missing exact-source gate: {fragment}")


def audit(root: Path | None = None) -> ReadinessReport:
    repository_root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    checks: list[str] = []

    project = tomllib.loads(_read(repository_root, "pyproject.toml"))["project"]
    version = str(project["version"])
    if version == PUBLIC_STABLE_VERSION:
        phase = "A"
    elif version == EXPECTED_CANDIDATE_VERSION:
        phase = "B"
    else:
        raise AssertionError(
            "2.2 pre-release package metadata must be exactly 2.1.0 (Phase A) "
            "or 2.2.0 (Phase B)"
        )
    checks.append(f"2.2 pre-release metadata matches Phase {phase}")
    runtime = _read(repository_root, "src/swirengine/__init__.py")
    _require(
        f'__version__ = "{version}"' in runtime,
        f"runtime __version__ matches package metadata {version}",
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
    urls = project.get("urls", {})
    if phase == "A":
        _require(
            str(urls.get("Roadmap", "")).endswith("ROADMAP_2_1.md"),
            "Phase A package metadata points at the immutable 2.1 roadmap",
            checks,
        )
    else:
        _require(
            str(urls.get("Roadmap", "")).endswith("ROADMAP_2_2.md"),
            "Phase B package metadata points at the active 2.2 roadmap",
            checks,
        )
        _require(
            str(urls.get("2.1 Roadmap", "")).endswith("ROADMAP_2_1.md"),
            "Phase B package metadata preserves the immutable 2.1 roadmap",
            checks,
        )

    roadmap_text = _read(repository_root, "ROADMAP_2_2.md")
    state = parse_roadmap(roadmap_text)
    require_phase_a_roadmap(roadmap_text, state)
    checks.append(f"2.2 roadmap remains exact 9/10 during Phase {phase}")

    validate_readme(
        _read(repository_root, "README.md"),
        state,
        root=repository_root,
        phase=phase,
    )
    checks.append("README preserves public 2.1.0 and exact active 2.2 progress")

    phase_files = (PHASE_A_WORKFLOW,) if phase == "A" else PHASE_B_FILES
    for relative in (
        REQUIRED_DOCS
        + REQUIRED_VERIFIERS
        + REQUIRED_FIXTURES
        + REQUIRED_WORKFLOWS
        + phase_files
    ):
        _read(repository_root, relative)
    checks.append("2.2 preflight docs, verifiers, fixtures and workflows are present")

    gate = _read(repository_root, "docs/RELEASE_GATE_2_2.md")
    _require(
        "Phase A — 9/10 exact-source preflight" in gate
        and "Only final Phase E acceptance may advance the roadmap to 10/10 = 100.0%" in gate,
        "2.2 release gate keeps roadmap completion behind final Phase E evidence",
        checks,
    )
    if phase == "A":
        _require(
            "Phase A evidence: pending exact-head CI" in gate,
            "2.2 release gate does not invent Phase A acceptance evidence",
            checks,
        )
    else:
        gate_words = " ".join(gate.split()).casefold()
        for fragment in (
            "6c109e2dce25d94dee91f5b06b84a134e4302d58",
            "a634e980649ec50307479ab0d14f483c77315e6a",
            "54/54",
            "47/47",
            "28/28",
            "bound non-publishing candidate",
        ):
            _require(
                fragment in gate_words,
                f"Phase B release gate records accepted Phase A evidence: {fragment}",
                checks,
            )
    migration = _read(repository_root, "docs/MIGRATING_TO_2_2.md")
    migration_words = " ".join(migration.split())
    if phase == "A":
        migration_ok = (
            "latest public stable release remains **SwirEngine 2.1.0**" in migration_words
            and "source development" in migration.casefold()
        )
    else:
        migration_folded = migration_words.casefold()
        migration_ok = (
            "latest public stable release remains **swirengine 2.1.0**" in migration_folded
            and "bound non-publishing candidate" in migration_folded
        )
    _require(
        migration_ok,
        f"2.2 migration guide preserves the Phase {phase} public-release boundary",
        checks,
    )

    workflow_path = PHASE_A_WORKFLOW if phase == "A" else PHASE_B_WORKFLOW
    workflow = _read(repository_root, workflow_path)
    validate_non_publishing_workflow(workflow, phase=phase)
    checks.append("dedicated 2.2 workflow is exact-source and non-publishing")

    _require(
        not (repository_root / ".release" / "publish-2.2.0").exists(),
        f"Phase {phase} publication marker is absent",
        checks,
    )

    return ReadinessReport(phase=phase, version=version, roadmap=state, checks=tuple(checks))


def main() -> int:
    report = audit()
    print(
        f"SwirEngine 2.2 Phase {report.phase} readiness OK: "
        f"version={report.version}, "
        f"roadmap={report.roadmap.completed}/{report.roadmap.total}, "
        f"progress={report.roadmap.percent:.1f}%, checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
