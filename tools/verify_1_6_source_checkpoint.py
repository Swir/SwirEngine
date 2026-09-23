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

REQUIRED_16_FILES = (
    "src/swirengine/multiplayer16.py",
    "src/swirengine/prediction16.py",
    "src/swirengine/session16.py",
    "src/swirengine/transport16.py",
    "src/swirengine/server16.py",
    "src/swirengine/content16.py",
    "src/swirengine/platform16.py",
    "src/swirengine/network_profiler16.py",
    "src/swirengine/multiplayer_showcase16.py",
    "tests/test_multiplayer_replication_1_6.py",
    "tests/test_prediction_reconciliation_1_6.py",
    "tests/test_session_lifecycle_1_6.py",
    "tests/test_transport_qos_1_6.py",
    "tests/test_dedicated_server_1_6.py",
    "tests/test_content_delivery_1_6.py",
    "tests/test_platform_services_1_6.py",
    "tests/test_network_profiler_1_6.py",
    "tests/test_multiplayer_showcase_soak_1_6.py",
    "examples/demo_multiplayer_replication_1_6.py",
    "examples/demo_prediction_reconciliation_1_6.py",
    "examples/demo_session_lifecycle_1_6.py",
    "examples/demo_transport_qos_1_6.py",
    "examples/demo_dedicated_server_1_6.py",
    "examples/demo_content_delivery_1_6.py",
    "examples/demo_platform_services_1_6.py",
    "examples/demo_network_profiler_1_6.py",
    "examples/demo_multiplayer_showcase_1_6.py",
    "tools/benchmark_multiplayer_replication_1_6.py",
    "tools/benchmark_prediction_reconciliation_1_6.py",
    "tools/benchmark_session_lifecycle_1_6.py",
    "tools/benchmark_transport_qos_1_6.py",
    "tools/benchmark_dedicated_server_1_6.py",
    "tools/benchmark_content_delivery_1_6.py",
    "tools/benchmark_platform_services_1_6.py",
    "tools/benchmark_network_profiler_1_6.py",
    "tools/benchmark_multiplayer_showcase_1_6.py",
    "docs/REPLICATION_STREAMING_2_1_6.md",
    "docs/PREDICTION_RECONCILIATION_2_1_6.md",
    "docs/SESSION_LOBBY_MATCH_LIFECYCLE_1_6.md",
    "docs/TRANSPORT_QOS_CHANNEL_POLICIES_1_6.md",
    "docs/DEDICATED_SERVER_RUNTIME_1_6.md",
    "docs/CONTENT_DELIVERY_1_6.md",
    "docs/PLATFORM_SERVICES_1_6.md",
    "docs/MULTIPLAYER_NETWORK_PROFILER_1_6.md",
    "docs/MULTIPLAYER_SHOWCASE_SOAK_1_6.md",
    ".github/workflows/multiplayer-replication-1-6.yml",
    ".github/workflows/prediction-reconciliation-1-6.yml",
    ".github/workflows/session-lifecycle-1-6.yml",
    ".github/workflows/transport-qos-1-6.yml",
    ".github/workflows/dedicated-server-1-6.yml",
    ".github/workflows/content-delivery-1-6.yml",
    ".github/workflows/platform-services-1-6.yml",
    ".github/workflows/network-profiler-1-6.yml",
    ".github/workflows/multiplayer-showcase-1-6.yml",
    "docs/RELEASE_HARDENING_1_6.md",
    ".github/workflows/source-checkpoint-1-6.yml",
    "tests/test_source_checkpoint_1_6.py",
)

LOCKED_COMPATIBILITY_FILES = (
    "tools/verify_1_3_release_candidate.py",
    "tools/verify_1_4_release_candidate.py",
    "tools/verify_1_5_release_candidate.py",
    "ROADMAP_1_3.md",
    "ROADMAP_1_4.md",
    "ROADMAP_1_5.md",
)

FORBIDDEN_16_PUBLICATION_FILES = (
    ".github/workflows/tag-1-6.yml",
    ".github/workflows/release-1-6.yml",
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


def validate_checkpoint(root: Path = PROJECT_ROOT, *, require_complete: bool = False) -> tuple[int, int]:
    roadmap = _read_text(root, "ROADMAP_1_6.md")
    checked, total = milestone_progress(roadmap)

    _assert(total == EXPECTED_MILESTONES, f"ROADMAP_1_6.md must contain exactly {EXPECTED_MILESTONES} milestones; found {total}")
    _assert(checked <= total, "roadmap completion count is invalid")

    if require_complete:
        _assert(checked == EXPECTED_MILESTONES, f"strict source checkpoint requires 10/10 milestones; found {checked}/{total}")
        _assert("100.0%" in roadmap and "10/10" in roadmap, "strict checkpoint requires the 100.0% / 10/10 roadmap marker")

    _assert("source-development checkpoint only" in roadmap, "ROADMAP_1_6.md must preserve the source-only checkpoint policy")
    _assert("SwirEngine 2.0" in roadmap, "ROADMAP_1_6.md must reserve the next public publication for SwirEngine 2.0")
    _assert("Do not create a `v1.6.0` tag" in roadmap, "ROADMAP_1_6.md must explicitly forbid a v1.6.0 release tag")

    project_version = _project_version(root)
    runtime_version = _runtime_version(root)
    allowed_versions = {STABLE_PUBLIC_VERSION}
    if _two_point_zero_finalized(root):
        allowed_versions.add(FORWARD_PUBLIC_VERSION)
    if _two_point_one_candidate_ready(root):
        allowed_versions.add(CANDIDATE_VERSION)
    _assert(
        project_version in allowed_versions,
        f"pyproject.toml must preserve the locked 1.6 history under {sorted(allowed_versions)}; found {project_version}",
    )
    _assert(
        runtime_version in allowed_versions,
        f"runtime __version__ must preserve the locked 1.6 history under {sorted(allowed_versions)}; found {runtime_version}",
    )
    _assert(project_version == runtime_version, "package and runtime versions must agree")

    for relative in REQUIRED_16_FILES + LOCKED_COMPATIBILITY_FILES:
        _assert((root / relative).is_file(), f"required source-checkpoint file is missing: {relative}")

    for relative in FORBIDDEN_16_PUBLICATION_FILES:
        _assert(not (root / relative).exists(), f"1.6 publication path is forbidden while Release/PyPI are frozen to 2.0: {relative}")

    hardening = _read_text(root, "docs/RELEASE_HARDENING_1_6.md")
    _assert("Release/PyPI: frozen until SwirEngine 2.0" in hardening, "hardening docs must preserve the 2.0 publication freeze")
    _assert("verify_1_6_source_checkpoint.py --require-complete" in hardening, "hardening docs must document the strict checkpoint auditor")

    workflow = _read_text(root, ".github/workflows/source-checkpoint-1-6.yml")
    _assert("verify_1_6_source_checkpoint.py" in workflow, "source-checkpoint workflow must run the auditor")
    _assert("benchmark_multiplayer_showcase_1_6.py" in workflow, "source-checkpoint workflow must include the 1.6 soak workload")
    _assert("python -m build" in workflow and "twine check" in workflow, "source-checkpoint workflow must validate wheel/sdist packaging")
    _assert("tag-1-6" not in workflow and "pypi" not in workflow.lower(), "source-checkpoint workflow must not contain a 1.6 publication path")

    return checked, total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the SwirEngine 1.6 source checkpoint without creating a release.")
    parser.add_argument("--require-complete", action="store_true", help="Require ROADMAP_1_6.md to be exactly 10/10.")
    args = parser.parse_args(argv)

    try:
        checked, total = validate_checkpoint(require_complete=args.require_complete)
    except (AssertionError, KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"SwirEngine 1.6 source checkpoint audit FAILED: {exc}", file=sys.stderr)
        return 1

    mode = "strict 10/10" if args.require_complete else "development"
    print(f"SwirEngine 1.6 source checkpoint audit passed ({mode}, roadmap {checked}/{total}).")
    print("Release/PyPI: frozen until SwirEngine 2.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
