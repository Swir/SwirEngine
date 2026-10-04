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
FORWARD_VERSION = "2.0.0"
CURRENT_PUBLIC_VERSION = "2.1.0"
CANDIDATE_VERSION = "2.2.0"
PATCH_CANDIDATE_VERSION = "2.2.1"
ACTIVE_STABLE_VERSIONS = {
    PREVIOUS_STABLE_VERSION,
    TARGET_VERSION,
    "1.5.0",
    FORWARD_VERSION,
    CURRENT_PUBLIC_VERSION,
    CANDIDATE_VERSION,
    PATCH_CANDIDATE_VERSION,
}
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


def _bound_two_point_two_candidate(root: Path) -> bool:
    readme_path = root / "README.md"
    notes_21_path = root / "RELEASE_NOTES_2_1.md"
    notes_22_path = root / "RELEASE_NOTES_2_2.md"
    roadmap_path = root / "ROADMAP_2_2.md"
    if not all(path.is_file() for path in (readme_path, notes_21_path, notes_22_path, roadmap_path)):
        return False
    readme = readme_path.read_text(encoding="utf-8")
    notes_21 = notes_21_path.read_text(encoding="utf-8")
    notes_22 = notes_22_path.read_text(encoding="utf-8")
    roadmap = roadmap_path.read_text(encoding="utf-8")
    history_ok = (
        notes_21.startswith("# SwirEngine 2.1.0 Release Notes")
        and "NOT PUBLISHED" not in notes_21
        and notes_22.startswith("# SwirEngine 2.2.0 Release Notes")
        and "Prepared from the bound 2.2.0 candidate" in notes_22
    )
    candidate_ok = (
        "Current verified progress: 9/10 milestones = 90.0%." in roadmap
        and "bound non-publishing candidate" in readme
        and "NOT PUBLISHED" in readme
        and "**Latest public stable release:** **SwirEngine 2.1.0**" in readme
        and '"swirengine==2.2.0"' not in readme
    )
    public_ok = (
        "Current verified progress: 10/10 milestones = 100.0%." in roadmap
        and "STATUS-2.2.0%20PUBLISHED" in readme
        and "**Latest public stable release:** **SwirEngine 2.2.0**" in readme
        and '"swirengine==2.2.0"' in readme
        and (root / "release-evidence/2.2.0/manifest.json").is_file()
        and (root / ".github/workflows/post-release-2.2.yml").is_file()
        and not (root / ".github/workflows/release-candidate-2.2.yml").exists()
    )
    return history_ok and (candidate_ok or public_ok)


def _bound_two_point_two_patch_candidate(root: Path) -> bool:
    readme_path = root / "README.md"
    notes_path = root / "RELEASE_NOTES_2_2.md"
    roadmap_path = root / "ROADMAP_2_2.md"
    if not all(path.is_file() for path in (readme_path, notes_path, roadmap_path)):
        return False
    readme = readme_path.read_text(encoding="utf-8")
    readme_folded = readme.casefold()
    notes = notes_path.read_text(encoding="utf-8")
    roadmap = roadmap_path.read_text(encoding="utf-8")
    return (
        notes.startswith("# SwirEngine 2.2.0 Release Notes")
        and "Prepared from the bound 2.2.0 candidate" in notes
        and "Current verified progress: 10/10 milestones = 100.0%." in roadmap
        and "swirengine 2.2.1" in readme_folded
        and "bound non-publishing patch candidate" in readme_folded
        and "NOT PUBLISHED" in readme
        and "**Latest public stable release:** **SwirEngine 2.2.0**" in readme
        and '"swirengine==2.2.0"' in readme
        and '"swirengine[audio]==2.2.0"' in readme
        and '"swirengine==2.2.1"' not in readme
        and '"swirengine[audio]==2.2.1"' not in readme
        and (root / "release-evidence/2.2.0/manifest.json").is_file()
    )


def _public_two_point_two_patch(root: Path) -> bool:
    required = (
        root / "README.md",
        root / "RELEASE_NOTES_2_2.md",
        root / "RELEASE_NOTES_2_2_1.md",
        root / "ROADMAP_2_2.md",
    )
    if not all(path.is_file() for path in required):
        return False
    readme = required[0].read_text(encoding="utf-8")
    notes_22 = required[1].read_text(encoding="utf-8")
    notes_221 = required[2].read_text(encoding="utf-8")
    roadmap = required[3].read_text(encoding="utf-8")
    return (
        notes_22.startswith("# SwirEngine 2.2.0 Release Notes")
        and "Prepared from the bound 2.2.0 candidate" in notes_22
        and notes_221.startswith("# SwirEngine 2.2.1 Release Notes")
        and "NOT PUBLISHED" not in notes_221
        and "Current verified progress: 10/10 milestones = 100.0%." in roadmap
        and "**Latest public stable release:** **SwirEngine 2.2.1**" in readme
        and '"swirengine==2.2.1"' in readme
        and '"swirengine[audio]==2.2.1"' in readme
        and "release-evidence/2.2.1/manifest.json" in readme
        and "NOT PUBLISHED" not in readme
        and (root / "release-evidence/2.2.1/manifest.json").is_file()
        and (root / ".github/workflows/post-release-2.2.1.yml").is_file()
        and not (root / ".github/workflows/release-candidate-2.2.1.yml").exists()
    )


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
    if version == CANDIDATE_VERSION:
        _require(
            _bound_two_point_two_candidate(root),
            "2.2.0 metadata is a bound non-publishing candidate over immutable public 2.1",
            checks,
        )
    elif version == PATCH_CANDIDATE_VERSION:
        _require(
            _bound_two_point_two_patch_candidate(root) or _public_two_point_two_patch(root),
            "2.2.1 metadata is a bound patch candidate or immutable public patch release",
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
            "later stable/candidate metadata preserves the locked 1.4 roadmap link",
            checks,
        )
        if version in {CANDIDATE_VERSION, PATCH_CANDIDATE_VERSION}:
            _require(
                str(urls.get("Roadmap", "")).endswith("/ROADMAP_2_2.md"),
                "2.2 candidate metadata points at the active 2.2 roadmap",
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
            version
            in {
                TARGET_VERSION,
                "1.5.0",
                FORWARD_VERSION,
                CURRENT_PUBLIC_VERSION,
                CANDIDATE_VERSION,
                PATCH_CANDIDATE_VERSION,
            },
            "complete 1.4 compatibility contract permits the 1.4 publication or later verified stable/candidate lines",
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
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
        in release,
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

    trigger_section = release.split("jobs:", 1)[0]
    if version == FORWARD_VERSION:
        _require(
            "workflow_dispatch:" in trigger_section,
            "2.0 publication recovery remains manually dispatchable",
            checks,
        )
        _require(
            "branches:\n      - main" in trigger_section
            and 'paths:\n      - ".github/workflows/release.yml"' in trigger_section,
            "2.0 automatic recovery is limited to the release workflow change on main",
            checks,
        )
        _require(
            "RELEASE_SHA: 4c219f3bed4c107c612a58fa2fb1f1362b4dfc46" in trigger_section
            and "RELEASE_TAG: v2.0.0" in trigger_section,
            "2.0 recovery is pinned to the immutable verified release source",
            checks,
        )
    elif version in {CURRENT_PUBLIC_VERSION, CANDIDATE_VERSION, PATCH_CANDIDATE_VERSION}:
        historical_release = _read(root, ".github/workflows/release-2.0.yml")
        for token in (
            'ref: "refs/tags/v2.0.0"',
            "verify_2_0_release_candidate.py --require-final",
            "swirengine==2.0.0",
            "pypa/gh-action-pypi-publish@release/v1",
        ):
            _require(
                token in historical_release,
                f"historical 2.0 publication workflow preserves {token}",
                checks,
            )
        if version == PATCH_CANDIDATE_VERSION:
            _require(
                "workflow_run:" in trigger_section,
                "2.2.1 patch publication remains behind an independent read-only gate",
                checks,
            )
        elif "RELEASE_TAG: v2.2.0" in trigger_section:
            publication_gate = _read(root, ".github/workflows/publication-gate-2.2.yml")
            for token in (
                "workflow_run:",
                "SwirEngine 2.2 Publication Gate",
                "verify_publication_chain_2_2.py",
                "verify_required_workflows_2_2.py",
                "reconcile_release_2_2.py",
            ):
                _require(
                    token in release,
                    f"current 2.2 publication workflow preserves {token}",
                    checks,
                )
            _require(
                'branches:\n      - "release/2.2.0-publication-r2"' in publication_gate,
                "2.2 publication gate is isolated to the dedicated publication branch",
                checks,
            )
        else:
            _require(
                "workflow_dispatch:" in trigger_section
                and "RELEASE_TAG: v2.1.0" in trigger_section
                and "verify_2_1_publication.py" in release
                and "verify_2_1_release_readiness.py" in release,
                "current 2.1 publication workflow is guarded by accepted 2.1 source contracts",
                checks,
            )
            _require(
                'branches:\n      - "release/2.1.0-publication"' in trigger_section,
                "2.1 publication workflow is isolated to the dedicated publication branch",
                checks,
            )
    else:
        _require(
            "branches:" not in trigger_section,
            "publication workflow has no main-branch publish trigger",
            checks,
        )
    _require(
        "git push --force" not in release and "git tag -f" not in release,
        "current publication workflow cannot force-move release history",
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
                "`v1.4.0`" in readme and "| 1.4 |" in readme and "released/locked" in readme,
                "later README preserves 1.4 as an immutable released/locked compatibility line",
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
