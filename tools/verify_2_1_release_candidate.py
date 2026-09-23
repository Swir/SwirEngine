from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "2.1.0"
PROGRESS_START = "<!-- SWIR-PYPI-PROGRESS:START -->"
PROGRESS_END = "<!-- SWIR-PYPI-PROGRESS:END -->"
WORKFLOW = ".github/workflows/release-candidate-2.1.yml"


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path.read_text(encoding="utf-8")


def _project_version(pyproject: str) -> str | None:
    project_match = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", pyproject)
    if project_match is None:
        return None
    version_match = re.search(
        r'^version\s*=\s*"([^"]+)"\s*$', project_match.group(1), re.MULTILINE
    )
    return version_match.group(1) if version_match else None


def _runtime_version(init_text: str) -> str | None:
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', init_text, re.MULTILINE)
    return match.group(1) if match else None


def check_release_candidate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    required = (
        "pyproject.toml",
        "src/swirengine/__init__.py",
        "ROADMAP_2_1.md",
        "README.md",
        "RELEASE_NOTES_2_1.md",
        "docs/RELEASE_GATE_2_1.md",
        WORKFLOW,
    )
    texts: dict[str, str] = {}
    for relative in required:
        try:
            texts[relative] = _read(root, relative)
        except FileNotFoundError:
            errors.append(f"missing required file: {relative}")

    if errors:
        return errors

    pyproject = texts["pyproject.toml"]
    if _project_version(pyproject) != EXPECTED_VERSION:
        errors.append(f"pyproject project version must be exactly {EXPECTED_VERSION}")
    if _runtime_version(texts["src/swirengine/__init__.py"]) != EXPECTED_VERSION:
        errors.append(f"runtime __version__ must be exactly {EXPECTED_VERSION}")
    if 'requires-python = ">=3.10,<3.15"' not in pyproject:
        errors.append("pyproject must retain the verified CPython 3.10-3.14 package range")

    roadmap = texts["ROADMAP_2_1.md"]
    if "Current verified progress: 10/10 milestones = 100.0%." not in roadmap:
        errors.append("ROADMAP_2_1.md must report 10/10 milestones = 100.0%")
    accepted = re.findall(r"(?m)^- \[x\] \*\*(\d+)\.", roadmap)
    if accepted != [str(index) for index in range(1, 11)]:
        errors.append("ROADMAP_2_1.md must contain accepted milestones 1 through 10 exactly once")

    readme = texts["README.md"]
    if readme.count(PROGRESS_START) != 1 or readme.count(PROGRESS_END) != 1:
        errors.append("README must contain exactly one SWIR-PYPI-PROGRESS marker pair")
    else:
        progress = readme.split(PROGRESS_START, 1)[1].split(PROGRESS_END, 1)[0]
        expected_lines = (
            "```text",
            "Scope: SwirEngine 2.1 - SwirEditor & Creator Workflow",
            "Progress: [##############################] 100.0%",
            "Counter: 10 / 10 milestones",
            "Status: COMPLETE",
            "```",
        )
        for line in expected_lines:
            if line not in progress:
                errors.append(f"PyPI progress block is missing exact line: {line}")
        forbidden_progress = ("<img", ".svg", "![", "<svg")
        if any(token in progress.lower() for token in forbidden_progress):
            errors.append("PyPI progress block must remain plain ASCII/text with no image or SVG")

    if "Latest public stable release:** **SwirEngine 2.0.0" not in readme:
        errors.append("README must keep public stable truth at SwirEngine 2.0.0 before publication")
    if "swirengine==2.0.0" not in readme:
        errors.append("README must keep the stable 2.0.0 install example before publication")
    if "swirengine==2.1.0" in readme:
        errors.append("README must not advertise a PyPI 2.1.0 install before publication")

    notes = texts["RELEASE_NOTES_2_1.md"]
    if "NOT PUBLISHED" not in notes:
        errors.append("2.1 release notes must explicitly state that the candidate is not published")
    if "public stable release remains SwirEngine 2.0.0" not in notes:
        errors.append("2.1 release notes must preserve public stable 2.0.0 truth")

    gate = texts["docs/RELEASE_GATE_2_1.md"]
    if "Phase C" not in gate:
        errors.append("2.1 release gate must preserve a separate Phase C publication decision")

    workflow = texts[WORKFLOW]
    required_workflow_tokens = (
        "permissions:",
        "contents: read",
        "push:",
        '"release/**"',
        "verify_2_1_release_candidate.py",
        "verify_2_1_release_readiness.py",
        "python -m build",
        "3.10",
        "3.11",
        "3.12",
        "3.13",
        "3.14",
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
    )
    for token in required_workflow_tokens:
        if token not in workflow:
            errors.append(f"candidate workflow is missing required token: {token}")

    forbidden_publish_tokens = (
        "pull_request:",
        "pypa/gh-action-pypi-publish",
        "twine upload",
        "gh release create",
        "git tag",
        "contents: write",
        "id-token: write",
    )
    for token in forbidden_publish_tokens:
        if token in workflow:
            errors.append(
                "candidate workflow must be release-branch-scoped and non-publishing; "
                f"forbidden token: {token}"
            )

    return errors


def main() -> int:
    errors = check_release_candidate()
    if errors:
        print("SwirEngine 2.1 release-candidate verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SwirEngine 2.1 release-candidate verification passed (non-publishing gate).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
