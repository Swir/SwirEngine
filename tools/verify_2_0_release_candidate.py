from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

TARGET_VERSION = "2.0.0"
PREVIOUS_STABLE_VERSION = "1.5.0"
EXPECTED_TOTAL = 10
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"

REQUIRED_DOCS = (
    "docs/API_STABILITY.md",
    "docs/MIGRATING_TO_2_0.md",
    "docs/CREATOR_WORKFLOW_2_0.md",
    "docs/MULTIPLAYER_PRODUCTION_2_0.md",
    "docs/RUNTIME_SCALABILITY_2_0.md",
    "docs/SUPPORT_MATRIX_2_0.md",
    "docs/REAL_GAME_SHIPPING_2_0.md",
    "docs/PACKAGING_SHIPPING_2_0.md",
    "docs/PERFORMANCE_EVIDENCE_2_0.md",
    "docs/RELEASE_SAFETY_2_0.md",
    "docs/RELEASE_GATE_2_0.md",
)

REQUIRED_VERIFIERS = (
    "tools/verify_2_0_public_api.py",
    "tools/verify_platform_matrix_2_0.py",
    "tools/verify_real_game_shipping_2_0.py",
    "tools/verify_packaging_shipping_2_0.py",
    "tools/verify_performance_evidence_2_0.py",
    "tools/verify_release_safety_2_0.py",
    "tools/generate_progress_svg.py",
)

REQUIRED_FIXTURES = (
    "examples/2d_game_demo/run_game.py",
    "examples/3d_game_demo/run_game.py",
    "examples/multiplayer_game_demo/run_game.py",
)


@dataclass(frozen=True, slots=True)
class RoadmapState:
    completed: int
    remaining: int
    total: int
    percent: float


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
    return RoadmapState(completed, remaining, total, percent)


def legacy_progress_meter_lines(text: str) -> tuple[str, ...]:
    matches: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if re.search(r"[█▓▒░■□]{5,}", line):
            matches.append(raw)
            continue
        if re.fullmatch(r"\[[#=\-]{5,}\](?:\s+.*)?", line):
            matches.append(raw)
    return tuple(matches)


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"required 2.0 release-contract file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def audit(root: Path | None = None, *, require_final: bool = False) -> AuditReport:
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    checks: list[str] = []

    project = tomllib.loads(_read(root, "pyproject.toml"))["project"]
    version = str(project["version"])
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

    roadmap_text = _read(root, "ROADMAP_2_0.md")
    roadmap = parse_roadmap(roadmap_text)
    _require(roadmap.total == EXPECTED_TOTAL, "2.0 roadmap has exactly 10 milestones", checks)

    readme = _read(root, "README.md")
    for label, text in (("README", readme), ("2.0 roadmap", roadmap_text)):
        _require(
            legacy_progress_meter_lines(text) == (),
            f"{label} contains no legacy character progress meter",
            checks,
        )

    _require(
        "<!-- SWIR-README-STANDARD:v2 -->" in readme,
        "README tracks SWIR README PRO v2",
        checks,
    )
    _require(
        "## 🔎 Search Keywords" in readme,
        "README keeps the required Search Keywords section",
        checks,
    )
    _require(
        'src="assets/readme/progress-card.svg"' in readme,
        "README embeds the project progress card",
        checks,
    )
    _require(
        'src="assets/readme/progress-mini.svg"' in roadmap_text,
        "2.0 roadmap embeds the compact progress SVG",
        checks,
    )
    for relative in (
        "assets/readme/progress-card.svg",
        "assets/readme/progress-mini.svg",
        "assets/readme/progress-template.svg",
    ):
        _read(root, relative)
        checks.append(f"required progress asset exists: {relative}")

    template = _read(root, "assets/readme/progress-template.svg")
    _require(
        "TEMPLATE" in template and "NOT PROJECT DATA" in template,
        "progress template is explicitly labelled TEMPLATE / NOT PROJECT DATA",
        checks,
    )

    init_text = _read(root, "src/swirengine/__init__.py")
    _require(
        f'__version__ = "{version}"' in init_text,
        "runtime __version__ matches project metadata",
        checks,
    )

    for relative in REQUIRED_DOCS + REQUIRED_VERIFIERS + REQUIRED_FIXTURES:
        _read(root, relative)
        checks.append(f"required 2.0 release artifact exists: {relative}")

    final_gate = _read(root, ".github/workflows/final-release-gate-2.0.yml")
    for token in (
        "verify_2_0_release_candidate.py",
        "verify_2_0_public_api.py",
        "verify_platform_matrix_2_0.py",
        "verify_real_game_shipping_2_0.py",
        "verify_packaging_shipping_2_0.py",
        "verify_performance_evidence_2_0.py",
        "verify_release_safety_2_0.py",
        "pytest",
        "ruff check",
        "compileall",
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
        '"3.10"',
        '"3.13"',
        '"3.14"',
    ):
        _require(token in final_gate, f"final 2.0 gate includes {token}", checks)

    release = _read(root, ".github/workflows/release-2.0.yml")
    for token in (
        '"v2.0.0"',
        "verify_2_0_release_candidate.py --require-final",
        "verify_2_0_public_api.py",
        "verify_platform_matrix_2_0.py",
        "verify_real_game_shipping_2_0.py",
        "verify_packaging_shipping_2_0.py",
        "verify_performance_evidence_2_0.py",
        "verify_release_safety_2_0.py",
        "RELEASE_NOTES_2_0.md",
        "swirengine==2.0.0",
        "pypa/gh-action-pypi-publish@release/v1",
        "id-token: write",
        "https://pypi.org/pypi/swirengine/2.0.0/json",
    ):
        _require(token in release, f"2.0 release workflow includes {token}", checks)
    _require(
        "skip-existing: true" not in release,
        "2.0 publication cannot hide duplicate artifacts",
        checks,
    )
    trigger = release.split("jobs:", 1)[0]
    _require("branches:" not in trigger, "2.0 publication workflow has no branch trigger", checks)

    tagger = _read(root, ".github/workflows/tag-2-0.yml")
    for token in (
        "release/2.0.0-publish",
        "verify_2_0_release_candidate.py --require-final",
        "git/ref/heads/main",
        "refs/tags/v2.0.0",
        '"$main_sha" != "$GITHUB_SHA"',
    ):
        _require(token in tagger, f"2.0 tag bridge includes {token}", checks)

    notes = _read(root, "RELEASE_NOTES_2_0.md")
    _require(TARGET_VERSION in notes, "2.0 release notes name version 2.0.0", checks)

    if require_final:
        _require(
            roadmap.completed == EXPECTED_TOTAL and roadmap.remaining == 0,
            "final 2.0 release requires exactly 10/10 milestones",
            checks,
        )
        _require(version == TARGET_VERSION, f"final package version is {TARGET_VERSION}", checks)
        urls = project.get("urls", {})
        _require(
            str(urls.get("Roadmap", "")).endswith("/ROADMAP_2_0.md"),
            "project metadata points at the 2.0 roadmap",
            checks,
        )
        _require(
            "10/10 milestones = 100.0%" in readme,
            "README reports verified 10/10 2.0 progress",
            checks,
        )
        _require(
            "STATUS-2.0.0%20STABLE" in readme,
            "README stable-status badge identifies 2.0.0",
            checks,
        )
        _require(
            "Release/PyPI: frozen until SwirEngine 2.0" not in readme,
            "README no longer presents the pre-release freeze after finalization",
            checks,
        )
    else:
        _require(
            roadmap.completed == 9 and roadmap.remaining == 1,
            "2.0 pre-release gate starts from exactly 9/10 verified milestones",
            checks,
        )
        _require(
            version == PREVIOUS_STABLE_VERSION,
            "public package metadata remains 1.5.0 before the final release step",
            checks,
        )
        _require(
            "9/10 milestones = 90.0%" in readme,
            "README reports the verified pre-release 9/10 state",
            checks,
        )
        _require(
            "Release/PyPI: frozen until SwirEngine 2.0" in readme,
            "README preserves the 2.0 publication freeze during preflight",
            checks,
        )

    return AuditReport(version=version, roadmap=roadmap, checks=tuple(checks))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the SwirEngine 2.0 final release-candidate contract."
    )
    parser.add_argument("--require-final", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(require_final=args.require_final)
    except (AssertionError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"2.0 RELEASE CONTRACT FAILED: {exc}")
        return 1
    print(
        "SwirEngine 2.0 release contract OK: "
        f"version={report.version}, roadmap={report.roadmap.completed}/{report.roadmap.total} "
        f"({report.roadmap.percent:.1f}%), checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
