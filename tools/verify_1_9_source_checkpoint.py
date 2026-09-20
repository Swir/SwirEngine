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
ACTIVE_20_ROADMAP = ROOT / "ROADMAP_2_0.md"
POST_RELEASE_STATUS = ROOT / "docs" / "SWIRENGINE_2_0_POST_RELEASE_AUDIT.md"
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOWS = ROOT / ".github" / "workflows"
READINESS_AUDIT = ROOT / "docs" / "SWIRENGINE_2_0_READINESS_AUDIT.md"
POST_RELEASE_MINI = "../assets/readme/progress-2-0-audit-mini.svg"

STABLE_PUBLIC_VERSION = "1.5.0"
FORWARD_PUBLIC_VERSION = "2.0.0"
EXPECTED_MILESTONES = 10

MILESTONE_RE = re.compile(r"^- \[([ xX])\] \*\*(\d+)\.", re.MULTILINE)
PROGRESS_RE = re.compile(
    r"Current verified progress:\s*(\d+)\s*/\s*(\d+)\s*milestones\s*=\s*([0-9]+(?:\.[0-9]+)?)%",
    re.IGNORECASE,
)
VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)

REQUIRED_19_FILES = (
    "src/swirengine/project19.py",
    "src/swirengine/shipping19.py",
    "src/swirengine/ui_navigation.py",
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


def _two_point_zero_finalized() -> bool:
    if not ACTIVE_20_ROADMAP.is_file():
        return False
    return "- [x] **10. SwirEngine 2.0 Final Release Gate & Public Verification**" in _text(
        ACTIVE_20_ROADMAP
    )


def _current_public_version() -> str:
    match = VERSION_RE.search(_text(PYPROJECT))
    if match is None:
        raise CheckpointError("pyproject.toml does not expose a static project version")
    return match.group(1)


def _post_release_audit_active() -> bool:
    if _current_public_version() != FORWARD_PUBLIC_VERSION or not POST_RELEASE_STATUS.is_file():
        return False
    readme = _text(README)
    return (
        "STATUS-2.0.0%20PUBLISHED" in readme
        and "**Latest public stable release:** **SwirEngine 2.0.0**" in readme
    )


def _verify_public_version() -> str:
    version = _current_public_version()
    allowed = {STABLE_PUBLIC_VERSION}
    if _two_point_zero_finalized():
        allowed.add(FORWARD_PUBLIC_VERSION)
    if version not in allowed:
        raise CheckpointError(
            "locked 1.9 history permits only the current public line or finalized 2.0: "
            f"allowed={sorted(allowed)}, found {version}"
        )
    return version


def _verify_release_freeze(roadmap_text: str) -> None:
    lowered = roadmap_text.lower()
    active_wording = "do not create `v1.9.0`, a github release, a release tag or a pypi publish"
    historical_wording = (
        "no `v1.9.0`, github release, release tag or pypi publication was created"
    )
    if active_wording not in lowered and historical_wording not in lowered:
        raise CheckpointError(
            "ROADMAP_1_9.md must explicitly preserve the no-1.9-publication contract"
        )
    if "next public github release and pypi publication remains swirengine 2.0" not in lowered:
        raise CheckpointError("ROADMAP_1_9.md does not preserve the 2.0-only next-release contract")
    if "release/pypi: frozen until swirengine 2.0" not in lowered:
        raise CheckpointError("ROADMAP_1_9.md does not preserve the explicit Release/PyPI freeze")

    forbidden = []
    for path in WORKFLOWS.glob("*.y*ml"):
        if any(pattern.search(path.name) for pattern in FORBIDDEN_19_WORKFLOW_PATTERNS):
            forbidden.append(path.name)
    if forbidden:
        raise CheckpointError(
            "intermediate 1.9 release/tag/publish workflows are forbidden: "
            + ", ".join(sorted(forbidden))
        )


def _embeds_progress_template(text: str) -> bool:
    return (
        'src="assets/readme/progress-template.svg"' in text
        or 'src="../assets/readme/progress-template.svg"' in text
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
    if _embeds_progress_template(readme) or _embeds_progress_template(roadmap):
        raise CheckpointError("progress-template.svg is a template and must never be embedded as real data")

    if ACTIVE_20_ROADMAP.is_file():
        roadmap_20 = _text(ACTIVE_20_ROADMAP)
        if not roadmap_20.startswith("<!-- SWIR-PROGRESS-SVG-PRO:v1 -->"):
            raise CheckpointError("ROADMAP_2_0.md must retain the SVG progress standard marker")
        if _embeds_progress_template(roadmap_20):
            raise CheckpointError("progress-template.svg is a template and must never be embedded as real data")
        if "assets/readme/progress-mini.svg" in roadmap:
            raise CheckpointError("historical ROADMAP_1_9.md must not reuse the active progress mini")

        if _post_release_audit_active():
            if "assets/readme/progress-mini.svg" in roadmap_20:
                raise CheckpointError(
                    "historical ROADMAP_2_0.md must not embed the active post-release progress mini"
                )
            status = _text(POST_RELEASE_STATUS)
            if status.count(POST_RELEASE_MINI) != 1:
                raise CheckpointError(
                    "active post-release audit must embed exactly one scoped audit progress mini"
                )
            if "../assets/readme/progress-mini.svg" in status:
                raise CheckpointError(
                    "active post-release audit must not reuse the active 2.1 progress mini"
                )
            if _embeds_progress_template(status):
                raise CheckpointError(
                    "progress-template.svg is a template and must never be embedded as real data"
                )
        elif roadmap_20.count("assets/readme/progress-mini.svg") != 1:
            raise CheckpointError("ROADMAP_2_0.md must embed exactly one authoritative progress mini")
    elif roadmap.count("assets/readme/progress-mini.svg") != 1:
        raise CheckpointError("ROADMAP_1_9.md must embed exactly one authoritative progress mini")


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
        public_version = _current_public_version()
    except CheckpointError as exc:
        print(f"source-checkpoint-1.9: FAIL: {exc}")
        return 1

    mode = "strict-complete" if args.require_complete else "development"
    print(
        "source-checkpoint-1.9: PASS "
        f"mode={mode} roadmap={state.completed}/{state.total} "
        f"progress={state.declared_percent:.1f}% public-version={public_version}"
    )
    if public_version == FORWARD_PUBLIC_VERSION and _two_point_zero_finalized():
        print("2.0-readiness: final release candidate")
    else:
        print("2.0-readiness: N/A until the dedicated 2.0 final gate succeeds")
    print("Release/PyPI: frozen until SwirEngine 2.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
