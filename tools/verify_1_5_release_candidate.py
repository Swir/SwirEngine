from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

TARGET_VERSION = "1.5.0"
PREVIOUS_STABLE_VERSION = "1.4.0"
EXPECTED_TOTAL = 10
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
REQUIRED_DOCS = (
    "docs/DETERMINISTIC_REPLAY_1_5.md",
    "docs/SAVE_PROFILE_2_1_5.md",
    "docs/AUDIO_2_1_5.md",
    "docs/ANIMATION_GRAPHS_2_1_5.md",
    "docs/NAVIGATION_2_1_5.md",
    "docs/WORLD_STREAMING_2_1_5.md",
    "docs/UI_TOOLKIT_2_1_5.md",
    "docs/EDITOR_PRODUCTIVITY_2_1_5.md",
    "docs/PERFORMANCE_DIAGNOSTICS_2_1_5.md",
    "docs/RELEASE_HARDENING_1_5.md",
)
REQUIRED_MODULES = (
    "src/swirengine/simulation15.py",
    "src/swirengine/storage15.py",
    "src/swirengine/audio15.py",
    "src/swirengine/animation15.py",
    "src/swirengine/navigation15.py",
    "src/swirengine/world_streaming15.py",
    "src/swirengine/world_streaming_easy15.py",
    "src/swirengine/ui15.py",
    "src/swirengine/editor15.py",
    "src/swirengine/performance15.py",
)
REQUIRED_BENCHMARKS = (
    "tools/benchmark_deterministic_replay_1_5.py",
    "tools/benchmark_save_profile_2_1_5.py",
    "tools/benchmark_audio_2_1_5.py",
    "tools/benchmark_animation_graphs_2_1_5.py",
    "tools/benchmark_navigation_2_1_5.py",
    "tools/benchmark_world_streaming_2_1_5.py",
    "tools/benchmark_ui_toolkit_2_1_5.py",
    "tools/benchmark_editor_productivity_1_5.py",
    "tools/benchmark_performance_diagnostics_2_1_5.py",
)
REQUIRED_DEMOS = (
    "examples/demo_deterministic_replay_1_5.py",
    "examples/demo_save_profile_2_1_5.py",
    "examples/demo_audio_2_1_5.py",
    "examples/demo_animation_graphs_2_1_5.py",
    "examples/demo_navigation_2_1_5.py",
    "examples/demo_world_streaming_2_1_5.py",
    "examples/demo_ui_toolkit_2_1_5.py",
    "examples/demo_editor_productivity_1_5.py",
    "examples/demo_performance_diagnostics_2_1_5.py",
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
        bar=f"{'█' * filled}{'░' * (20 - filled)} {percent:.1f}% — {completed}/{total}",
    )


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"required 1.5 release-contract file is missing: {relative}")
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

    roadmap_text = _read(root, "ROADMAP_1_5.md")
    roadmap = parse_roadmap(roadmap_text)
    _require(roadmap.total == EXPECTED_TOTAL, "1.5 roadmap has exactly 10 milestones", checks)
    _require(roadmap.bar in roadmap_text, "roadmap progress bar matches milestone checkboxes", checks)
    _require(
        "SwirEngine 1.5 must not be tagged or published until all 10 milestones are complete"
        in roadmap_text,
        "roadmap preserves the no-early-publication rule",
        checks,
    )

    if require_complete:
        _require(
            roadmap.completed == 10 and roadmap.remaining == 0,
            "1.5 release requires exactly 10/10 milestones",
            checks,
        )
        _require(version == TARGET_VERSION, f"final package version is {TARGET_VERSION}", checks)
        urls = project.get("urls", {})
        _require(
            str(urls.get("Roadmap", "")).endswith("/ROADMAP_1_5.md"),
            "project metadata points at the 1.5 roadmap",
            checks,
        )
    else:
        _require(
            roadmap.completed in {9, 10},
            "1.5 hardening phase must be at milestone 9 or 10",
            checks,
        )
        _require(
            version in {PREVIOUS_STABLE_VERSION, TARGET_VERSION},
            f"package version is valid for 1.5 hardening: {version}",
            checks,
        )
        if roadmap.completed < 10:
            _require(
                version == PREVIOUS_STABLE_VERSION,
                "stable package remains 1.4.0 before 10/10",
                checks,
            )

    init_text = _read(root, "src/swirengine/__init__.py")
    _require(
        f'__version__ = "{version}"' in init_text,
        "runtime __version__ matches project metadata",
        checks,
    )

    for relative in REQUIRED_DOCS + REQUIRED_MODULES + REQUIRED_BENCHMARKS + REQUIRED_DEMOS:
        _read(root, relative)
        checks.append(f"required 1.5 artifact exists: {relative}")

    for relative in (
        "examples/2d_game_demo/run_game.py",
        "examples/2d_game_demo/README.md",
        "examples/3d_game_demo/run_game.py",
        "examples/3d_game_demo/README.md",
    ):
        _read(root, relative)
        checks.append(f"source-only game showcase exists: {relative}")

    hardening = _read(root, ".github/workflows/showcase-hardening-1-5.yml")
    for token in (
        "verify_1_5_release_candidate.py",
        "verify_1_3_release_candidate.py",
        "verify_1_4_release_candidate.py --require-complete",
        "pytest",
        "ruff check",
        "compileall",
        "SWIR_GAME_DEMO_HEADLESS",
        "SWIR_GAME_DEMO_SMOKE_FRAMES",
        "xvfb-run",
        "python -m build",
        "      - main",
    ) + tuple(Path(item).name for item in REQUIRED_BENCHMARKS):
        _require(token in hardening, f"1.5 hardening workflow includes {token}", checks)

    ci = _read(root, ".github/workflows/ci.yml")
    _require(
        "verify_1_3_release_candidate.py" in ci,
        "historical 1.3 compatibility contract remains protected",
        checks,
    )
    _require(
        "verify_1_4_release_candidate.py --require-complete" in ci,
        "locked 1.4 release contract remains protected",
        checks,
    )
    _require(
        "verify_1_5_release_candidate.py" in ci,
        "normal CI audits the active 1.5 release contract",
        checks,
    )

    if require_complete:
        _require(
            "verify_1_5_release_candidate.py --require-complete" in ci,
            "normal CI uses the complete 1.5 contract after 10/10",
            checks,
        )

        release = _read(root, ".github/workflows/release.yml")
        for token in (
            '"v1.5.0"',
            "verify_1_5_release_candidate.py --require-complete",
            "verify_1_3_release_candidate.py",
            "verify_1_4_release_candidate.py --require-complete",
            "RELEASE_NOTES_1_5.md",
            "swirengine==1.5.0",
            "pypa/gh-action-pypi-publish@release/v1",
            "id-token: write",
            "examples/2d_game_demo/run_game.py",
            "examples/3d_game_demo/run_game.py",
            "SWIR_GAME_DEMO_SMOKE_FRAMES",
            "xvfb-run",
            "dist-base\\swirengine-1.5.0-py3-none-any.whl",
            "https://pypi.org/pypi/swirengine/1.5.0/json",
        ) + tuple(Path(item).name for item in REQUIRED_BENCHMARKS):
            _require(token in release, f"release workflow includes {token}", checks)
        _require(
            "skip-existing: true" not in release,
            "publication cannot hide duplicate artifacts",
            checks,
        )
        _require(
            "branches:" not in release.split("jobs:", 1)[0],
            "publication workflow has no branch publish trigger",
            checks,
        )

        tagger = _read(root, ".github/workflows/tag-1-5.yml")
        for token in (
            "release/1.5.0-publish",
            "verify_1_5_release_candidate.py --require-complete",
            "git/ref/heads/main",
            'refs/tags/v1.5.0',
            '"$main_sha" != "$GITHUB_SHA"',
        ):
            _require(token in tagger, f"1.5 tag bridge includes {token}", checks)

        readme = _read(root, "README.md")
        _require("# SwirEngine 1.5.0" in readme, "README title matches 1.5.0", checks)
        _require("10/10 = 100.0%" in readme, "README reports verified 10/10 progress", checks)
        _require(
            "Runtime Diagnostics & Profiling 2.0" in readme,
            "README documents milestone 9",
            checks,
        )
        notes = _read(root, "RELEASE_NOTES_1_5.md")
        _require(TARGET_VERSION in notes, "1.5 release notes name the release version", checks)

    return AuditReport(version=version, roadmap=roadmap, checks=tuple(checks))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the SwirEngine 1.5 release-candidate contract."
    )
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(require_complete=args.require_complete)
    except (AssertionError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"1.5 RELEASE CONTRACT FAILED: {exc}")
        return 1
    print(
        "SwirEngine 1.5 release contract OK: "
        f"version={report.version}, roadmap={report.roadmap.completed}/{report.roadmap.total} "
        f"({report.roadmap.percent:.1f}%), checks={len(report.checks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
