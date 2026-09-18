"""Audit the SwirEngine 1.9 source-only checkpoint and 2.0-readiness contract.

Development mode validates the checkpoint infrastructure while Milestone 10 is still open.
``--require-complete`` is intentionally strict and refuses to pass until the authoritative
1.9 roadmap is exactly 10/10 = 100.0%. This tool never publishes, tags, or mutates releases.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "ROADMAP_1_9.md"
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOWS = ROOT / ".github" / "workflows"
READINESS_AUDIT = ROOT / "docs" / "SWIRENGINE_2_0_READINESS_AUDIT.md"

STABLE_PUBLIC_VERSION = "1.5.0"
EXPECTED_MILESTONES = 10

MILESTONE_RE = re.compile(r"^- \[([ xX])\] \*\*(\d+)\.", re.MULTILINE)
PROGRESS_RE = re.compile(
    r"Current verified progress:\s*(\d+)\s*/\s*(\d+)\s*milestones\s*=\s*([0-9]+(?:\.[0-9]+)?)%",
    re.IGNORECASE,
)
VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)

REQUIRED_19_FILES = (
    "src/swirengine/project19.py",
    "src/swirengine/input19.py",
    "src/swirengine/ui19.py",
    "src/swirengine/settings19.py",
    "src/swirengine/game_state19.py",
    "src/swirengine/scene_packages19.py",
    "src/swirengine/content_build19.py",
    "src/swirengine/diagnostics19.py",
    "src/swirengine/desktop_shipping19.py",
    "examples/2d_game_demo/run_game.py",
    "examples/3d_game_demo/run_game.py",
    "examples/multiplayer_game_demo/run_game.py",
    "tools/verify_real_game_production_1_9.py",
    "tools/verify_clean_desktop_shipping_1_9.py",
    "tools/generate_progress_svg.py",
    "assets/readme/progress-card.svg",
    "assets/readme/progress-mini.svg",
    "assets/readme/progress-template.svg",
    "docs/SWIRENGINE_2_0_READINESS_AUDIT.md",
    "tests/test_source_checkpoint_1_9.py",
    ".github/workflows/source-checkpoint-1-9.yml",
    "CHANGELOG.d/1.9-source-checkpoint.md",
)

REQUIRED_19_WORKFLOWS = (
    "project-production-1-9.yml",
    "run-session-1-9.yml",
    "input-ui-settings-1-9.yml",
    "game-state-production-1-9.yml",
    "scene-packages-1-9.yml",
    "content-build-1-9.yml",
    "runtime-diagnostics-1-9.yml",
    "desktop-shipping-1-9.yml",
    "real-game-production-1-9.yml",
    "source-checkpoint-1-9.yml",
)

LOCKED_COMPATIBILITY_FILES = (
    "ROADMAP_1_4.md",
    "ROADMAP_1_5.md",
    "ROADMAP_1_6.md",
    "ROADMAP_1_7.md",
    "ROADMAP_1_8.md",
    "tools/verify_1_6_source_checkpoint.py",
    "tools/verify_1_7_source_checkpoint.py",
    "tools/verify_1_8_source_checkpoint.py",
    ".github/workflows/showcase-hardening-1-4.yml",
    ".github/workflows/showcase-hardening-1-5.yml",
    ".github/workflows/source-checkpoint-1-6.yml",
    ".github/workflows/source-checkpoint-1-7.yml",
    ".github/workflows/source-checkpoint-1-8.yml",
)

FORBIDDEN_19_WORKFLOW_PATTERNS = (
    re.compile(r"(?:release|publish|tag).*1[-_.]?9", re.IGNORECASE),
    re.compile(r"1[-_.]?9.*(?:release|publish|tag)", re.IGNORECASE),
)


class CheckpointError(RuntimeError):
    """Raised when the 1.9 source checkpoint contract is violated."""


@dataclass(frozen=True)
class RoadmapState:
    completed: int
    total: int
    declared_completed: int
    declared_total: int
    declared_percent: float

    @property
    def calculated_percent(self) -> float:
        return (self.completed / self.total) * 100.0 if self.total else 0.0


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CheckpointError(f"required file is missing: {path.relative_to(ROOT)}") from exc


def parse_roadmap(text: str) -> RoadmapState:
    milestones = MILESTONE_RE.findall(text)
    if len(milestones) != EXPECTED_MILESTONES:
        raise CheckpointError(
            f"ROADMAP_1_9.md must contain exactly {EXPECTED_MILESTONES} numbered milestones; "
            f"found {len(milestones)}"
        )

    numbers = [int(number) for _, number in milestones]
    expected_numbers = list(range(1, EXPECTED_MILESTONES + 1))
    if numbers != expected_numbers:
        raise CheckpointError(
            f"ROADMAP_1_9.md milestone numbering must be {expected_numbers}; found {numbers}"
        )

    completed = sum(mark.lower() == "x" for mark, _ in milestones)
    match = PROGRESS_RE.search(text)
    if match is None:
        raise CheckpointError("ROADMAP_1_9.md is missing the verified progress declaration")

    state = RoadmapState(
        completed=completed,
        total=len(milestones),
        declared_completed=int(match.group(1)),
        declared_total=int(match.group(2)),
        declared_percent=float(match.group(3)),
    )
    if state.declared_completed != state.completed or state.declared_total != state.total:
        raise CheckpointError(
            "ROADMAP_1_9.md progress declaration does not match milestone checkboxes: "
            f"declared {state.declared_completed}/{state.declared_total}, "
            f"calculated {state.completed}/{state.total}"
        )
    if abs(state.declared_percent - state.calculated_percent) > 0.05:
        raise CheckpointError(
            "ROADMAP_1_9.md percentage does not match milestone checkboxes: "
            f"declared {state.declared_percent:.1f}%, "
            f"calculated {state.calculated_percent:.1f}%"
        )
    return state


def _require_files(paths: tuple[str, ...], *, label: str) -> None:
    missing = [path for path in paths if not (ROOT / path).is_file()]
    if missing:
        raise CheckpointError(f"missing {label}: " + ", ".join(missing))


def _verify_public_version() -> None:
    match = VERSION_RE.search(_text(PYPROJECT))
    if match is None:
        raise CheckpointError("pyproject.toml does not expose a static project version")
    if match.group(1) != STABLE_PUBLIC_VERSION:
        raise CheckpointError(
            "source-only 1.9 development must keep the public package frozen at "
            f"{STABLE_PUBLIC_VERSION}; found {match.group(1)}"
        )


def _verify_release_freeze(roadmap_text: str) -> None:
    lowered = roadmap_text.lower()
    required = (
        "do not create `v1.9.0`, a github release, a release tag or a pypi publish",
        "next public github release and pypi publication remains swirengine 2.0 only",
    )
    missing = [token for token in required if token not in lowered]
    if missing:
        raise CheckpointError("ROADMAP_1_9.md does not preserve the 2.0-only release freeze")

    forbidden = []
    for path in WORKFLOWS.glob("*.y*ml"):
        if any(pattern.search(path.name) for pattern in FORBIDDEN_19_WORKFLOW_PATTERNS):
            forbidden.append(path.name)
    if forbidden:
        raise CheckpointError(
            "intermediate 1.9 release/tag/publish workflows are forbidden: "
            + ", ".join(sorted(forbidden))
        )


def _verify_visual_contract() -> None:
    readme = _text(README)
    roadmap = _text(ROADMAP)
    if not readme.startswith("<!-- SWIR-README-STANDARD:v2 -->"):
        raise CheckpointError("README.md must retain SWIR README standard v2")
    if not roadmap.startswith("<!-- SWIR-PROGRESS-SVG-PRO:v1 -->"):
        raise CheckpointError("ROADMAP_1_9.md must retain the SVG progress standard marker")
    if readme.count("assets/readme/progress-card.svg") != 1:
        raise CheckpointError("README.md must embed exactly one authoritative progress card")
    if roadmap.count("assets/readme/progress-mini.svg") != 1:
        raise CheckpointError("ROADMAP_1_9.md must embed exactly one authoritative progress mini")
    if "progress-template.svg" in readme or "progress-template.svg" in roadmap:
        raise CheckpointError("progress-template.svg is a template and must never be embedded as real data")


def _verify_readiness_audit() -> None:
    audit = _text(READINESS_AUDIT)
    required = (
        "# SwirEngine 2.0 Readiness Audit",
        "## Verified 1.9 foundations",
        "## Evidence-backed gaps before 2.0",
        "## 2.0 readiness status",
        "N/A",
        "Release/PyPI: frozen until SwirEngine 2.0",
    )
    missing = [token for token in required if token not in audit]
    if missing:
        raise CheckpointError(
            "SWIRENGINE_2_0_READINESS_AUDIT.md is missing required evidence sections: "
            + ", ".join(missing)
        )


def _verify_workflows() -> None:
    missing = [name for name in REQUIRED_19_WORKFLOWS if not (WORKFLOWS / name).is_file()]
    if missing:
        raise CheckpointError("missing 1.9 validation workflows: " + ", ".join(missing))

    checkpoint = _text(WORKFLOWS / "source-checkpoint-1-9.yml")
    required_tokens = (
        '"3.10"',
        '"3.13"',
        '"3.14"',
        "verify_1_9_source_checkpoint.py",
        "verify_1_8_source_checkpoint.py --require-complete",
        "generate_progress_svg.py --check",
        "python -m build",
        "twine check",
        "verify_real_game_production_1_9.py --staging-only",
        "verify_clean_desktop_shipping_1_9.py --wheelhouse wheelhouse",
    )
    missing_tokens = [token for token in required_tokens if token not in checkpoint]
    if missing_tokens:
        raise CheckpointError(
            "source-checkpoint-1-9.yml is missing required validation contracts: "
            + ", ".join(missing_tokens)
        )

    lowered = checkpoint.lower()
    forbidden_publish_tokens = (
        "twine upload",
        "gh release",
        "pypa/gh-action-pypi-publish",
        "git tag",
    )
    found = [token for token in forbidden_publish_tokens if token in lowered]
    if found:
        raise CheckpointError(
            "source-checkpoint-1-9.yml must validate only and never publish: " + ", ".join(found)
        )


def audit(*, require_complete: bool = False) -> RoadmapState:
    roadmap_text = _text(ROADMAP)
    state = parse_roadmap(roadmap_text)

    _require_files(REQUIRED_19_FILES, label="1.9 checkpoint files")
    _require_files(LOCKED_COMPATIBILITY_FILES, label="locked 1.4-1.8 compatibility files")
    _verify_public_version()
    _verify_release_freeze(roadmap_text)
    _verify_visual_contract()
    _verify_readiness_audit()
    _verify_workflows()

    if require_complete and (
        state.completed != EXPECTED_MILESTONES
        or state.total != EXPECTED_MILESTONES
        or abs(state.declared_percent - 100.0) > 0.05
    ):
        raise CheckpointError(
            "strict 1.9 source checkpoint refuses completion below 10/10 = 100.0%; "
            f"current roadmap is {state.completed}/{state.total} = {state.declared_percent:.1f}%"
        )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="refuse to pass until ROADMAP_1_9.md is exactly 10/10 = 100.0%%",
    )
    args = parser.parse_args()

    try:
        state = audit(require_complete=args.require_complete)
    except CheckpointError as exc:
        print(f"source-checkpoint-1.9: FAIL: {exc}")
        return 1

    mode = "strict-complete" if args.require_complete else "development"
    print(
        "source-checkpoint-1.9: PASS "
        f"mode={mode} roadmap={state.completed}/{state.total} "
        f"progress={state.declared_percent:.1f}% public-version={STABLE_PUBLIC_VERSION}"
    )
    print("2.0-readiness: N/A until the dedicated 2.0 roadmap and final gate exist")
    print("Release/PyPI: frozen until SwirEngine 2.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
