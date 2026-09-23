from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STABLE_PUBLIC_VERSION = "1.5.0"
FORWARD_PUBLIC_VERSION = "2.0.0"
CANDIDATE_VERSION = "2.1.0"
EXPECTED_MILESTONES = 10

MILESTONE_RE = re.compile(r"^- \[([ x])\] \*\*(\d+)\.", re.MULTILINE)

REQUIRED_17_FILES = (
    "src/swirengine/jobs17.py",
    "src/swirengine/assets17.py",
    "src/swirengine/resource_budget17.py",
    "src/swirengine/work_graph17.py",
    "src/swirengine/scene_staging17.py",
    "src/swirengine/background_save17.py",
    "src/swirengine/shader_cache17.py",
    "src/swirengine/frame_budget17.py",
    "tests/test_background_jobs_1_7.py",
    "tests/test_async_assets_1_7.py",
    "tests/test_resource_budget_1_7.py",
    "tests/test_work_graph_1_7.py",
    "tests/test_scene_staging_1_7.py",
    "tests/test_background_save_1_7.py",
    "tests/test_shader_cache_1_7.py",
    "tests/test_frame_budget_1_7.py",
    "examples/demo_background_jobs_1_7.py",
    "examples/demo_async_assets_1_7.py",
    "examples/demo_resource_budget_1_7.py",
    "examples/demo_work_graph_1_7.py",
    "examples/demo_scene_staging_1_7.py",
    "examples/demo_background_save_1_7.py",
    "examples/demo_shader_cache_1_7.py",
    "examples/demo_frame_budget_1_7.py",
    "examples/demo_parallel_runtime_showcase_1_7.py",
    "tools/benchmark_background_jobs_1_7.py",
    "tools/benchmark_async_assets_1_7.py",
    "tools/benchmark_resource_budget_1_7.py",
    "tools/benchmark_work_graph_1_7.py",
    "tools/benchmark_scene_staging_1_7.py",
    "tools/benchmark_background_save_1_7.py",
    "tools/benchmark_shader_cache_1_7.py",
    "tools/benchmark_frame_budget_1_7.py",
    "tools/soak_parallel_runtime_1_7.py",
    ".github/workflows/background-jobs-1-7.yml",
    ".github/workflows/async-assets-1-7.yml",
    ".github/workflows/resource-budget-1-7.yml",
    ".github/workflows/streaming-work-graph-1-7.yml",
    ".github/workflows/scene-staging-1-7.yml",
    ".github/workflows/background-save-1-7.yml",
    ".github/workflows/shader-material-cache-1-7.yml",
    ".github/workflows/frame-budget-1-7.yml",
    ".github/workflows/parallel-runtime-showcase-1-7.yml",
    "docs/PARALLEL_RUNTIME_SHOWCASE_1_7.md",
    "docs/RELEASE_HARDENING_1_7.md",
    ".github/workflows/source-checkpoint-1-7.yml",
    "tests/test_source_checkpoint_1_7.py",
)

LOCKED_COMPATIBILITY_FILES = (
    "tools/verify_1_3_release_candidate.py",
    "tools/verify_1_4_release_candidate.py",
    "tools/verify_1_5_release_candidate.py",
    "tools/verify_1_6_source_checkpoint.py",
    "ROADMAP_1_3.md",
    "ROADMAP_1_4.md",
    "ROADMAP_1_5.md",
    "ROADMAP_1_6.md",
    ".github/workflows/source-checkpoint-1-6.yml",
)

FORBIDDEN_17_PUBLICATION_FILES = (
    ".github/workflows/tag-1-7.yml",
    ".github/workflows/release-1-7.yml",
)


def _read_text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def milestone_progress(roadmap_text: str) -> tuple[int, int]:
    matches = MILESTONE_RE.findall(roadmap_text)
    checked = sum(mark == "x" for mark, _number in matches)
    return checked, len(matches)


def _project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _runtime_version(root: Path) -> str:
    init_text = _read_text(root, "src/swirengine/__init__.py")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    _assert(match is not None, "src/swirengine/__init__.py must declare __version__")
    return match.group(1)


def _two_point_zero_finalized(root: Path) -> bool:
    roadmap = root / "ROADMAP_2_0.md"
    if not roadmap.is_file():
        return False
    return "- [x] **10. SwirEngine 2.0 Final Release Gate & Public Verification**" in roadmap.read_text(
        encoding="utf-8"
    )


def _two_point_one_candidate_ready(root: Path) -> bool:
    roadmap = root / "ROADMAP_2_1.md"
    notes = root / "RELEASE_NOTES_2_1.md"
    if not roadmap.is_file() or not notes.is_file():
        return False
    roadmap_text = roadmap.read_text(encoding="utf-8")
    notes_text = notes.read_text(encoding="utf-8")
    return (
        "Current verified progress: 10/10 milestones = 100.0%." in roadmap_text
        and "NOT PUBLISHED" in notes_text
    )


def _assert_locked_roadmap(root: Path, version: str) -> None:
    text = _read_text(root, f"ROADMAP_{version.replace('.', '_')}.md")
    _assert("100.0%" in text, f"locked {version} roadmap must preserve its 100.0% completion marker")
    _assert(
        "10/10" in text or "DONE-10%2F10" in text,
        f"locked {version} roadmap must preserve its 10/10 completion marker",
    )
    if version == "1.6":
        checked, total = milestone_progress(text)
        _assert(
            (checked, total) == (EXPECTED_MILESTONES, EXPECTED_MILESTONES),
            f"locked {version} roadmap must remain 10/10; found {checked}/{total}",
        )


def validate_checkpoint(root: Path = PROJECT_ROOT, *, require_complete: bool = False) -> tuple[int, int]:
    roadmap = _read_text(root, "ROADMAP_1_7.md")
    checked, total = milestone_progress(roadmap)

    _assert(total == EXPECTED_MILESTONES, f"ROADMAP_1_7.md must contain exactly {EXPECTED_MILESTONES} milestones; found {total}")
    _assert(checked <= total, "roadmap completion count is invalid")

    if require_complete:
        _assert(checked == EXPECTED_MILESTONES, f"strict source checkpoint requires 10/10 milestones; found {checked}/{total}")
        _assert("100.0%" in roadmap and "10/10" in roadmap, "strict checkpoint requires the 100.0% / 10/10 roadmap marker")

    _assert("source-development checkpoints only" in roadmap, "ROADMAP_1_7.md must preserve the source-only checkpoint policy")
    _assert("SwirEngine 2.0" in roadmap, "ROADMAP_1_7.md must reserve the next public publication for SwirEngine 2.0")
    _assert("Do not create a `v1.7.0` tag" in roadmap, "ROADMAP_1_7.md must explicitly forbid a v1.7.0 release tag")

    project_version = _project_version(root)
    runtime_version = _runtime_version(root)
    allowed_versions = {STABLE_PUBLIC_VERSION}
    if _two_point_zero_finalized(root):
        allowed_versions.add(FORWARD_PUBLIC_VERSION)
    if _two_point_one_candidate_ready(root):
        allowed_versions.add(CANDIDATE_VERSION)
    _assert(
        project_version in allowed_versions,
        f"pyproject.toml must preserve the locked 1.7 history under {sorted(allowed_versions)}; found {project_version}",
    )
    _assert(
        runtime_version in allowed_versions,
        f"runtime __version__ must preserve the locked 1.7 history under {sorted(allowed_versions)}; found {runtime_version}",
    )
    _assert(project_version == runtime_version, "package and runtime versions must agree")

    for relative in REQUIRED_17_FILES + LOCKED_COMPATIBILITY_FILES:
        _assert((root / relative).is_file(), f"required source-checkpoint file is missing: {relative}")

    for relative in FORBIDDEN_17_PUBLICATION_FILES:
        _assert(not (root / relative).exists(), f"1.7 publication path is forbidden while Release/PyPI are frozen to 2.0: {relative}")

    for version in ("1.3", "1.4", "1.5", "1.6"):
        _assert_locked_roadmap(root, version)

    hardening = _read_text(root, "docs/RELEASE_HARDENING_1_7.md")
    _assert("Release/PyPI: frozen until SwirEngine 2.0" in hardening, "hardening docs must preserve the 2.0 publication freeze")
    _assert("verify_1_7_source_checkpoint.py --require-complete" in hardening, "hardening docs must document the strict checkpoint auditor")

    workflow = _read_text(root, ".github/workflows/source-checkpoint-1-7.yml")
    _assert("verify_1_7_source_checkpoint.py" in workflow, "source-checkpoint workflow must run the 1.7 auditor")
    _assert("verify_1_6_source_checkpoint.py --require-complete" in workflow, "source-checkpoint workflow must revalidate the 1.6 checkpoint")
    _assert("soak_parallel_runtime_1_7.py" in workflow, "source-checkpoint workflow must include the integrated 1.7 soak")
    _assert("python -m build" in workflow and "twine check" in workflow, "source-checkpoint workflow must validate wheel/sdist packaging")
    _assert("tag-1-7" not in workflow and "publish" not in workflow.lower(), "source-checkpoint workflow must not contain a 1.7 publication path")

    release_workflow = _read_text(root, ".github/workflows/release.yml")
    _assert("v1.7.0" not in release_workflow, "general release workflow must not gain a v1.7.0 publication path")

    return checked, total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the SwirEngine 1.7 source checkpoint without creating a release.")
    parser.add_argument("--require-complete", action="store_true", help="Require ROADMAP_1_7.md to be exactly 10/10.")
    args = parser.parse_args(argv)

    try:
        checked, total = validate_checkpoint(require_complete=args.require_complete)
    except (AssertionError, KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"SwirEngine 1.7 source checkpoint audit FAILED: {exc}", file=sys.stderr)
        return 1

    mode = "strict 10/10" if args.require_complete else "development"
    print(f"SwirEngine 1.7 source checkpoint audit passed ({mode}, roadmap {checked}/{total}).")
    print("Release/PyPI: frozen until SwirEngine 2.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
