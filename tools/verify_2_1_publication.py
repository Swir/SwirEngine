from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on CPython 3.10
    import tomli as tomllib

PROGRESS_START = "<!-- SWIR-PYPI-PROGRESS:START -->"
PROGRESS_END = "<!-- SWIR-PYPI-PROGRESS:END -->"
EXPECTED_BLOCK = """<!-- SWIR-PYPI-PROGRESS:START -->
```text
Scope: SwirEngine 2.1 - SwirEditor & Creator Workflow
Progress: [##############################] 100.0%
Counter: 10 / 10 milestones
Status: COMPLETE
```
<!-- SWIR-PYPI-PROGRESS:END -->"""


def verify(root: Path) -> list[str]:
    errors: list[str] = []
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    readme = (root / "README.md").read_text(encoding="utf-8")
    notes = (root / "RELEASE_NOTES_2_1.md").read_text(encoding="utf-8")
    roadmap = (root / "ROADMAP_2_1.md").read_text(encoding="utf-8")
    release = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")

    if pyproject["project"]["version"] != "2.1.0":
        errors.append("pyproject project.version must be 2.1.0 for publication")

    if readme.count(PROGRESS_START) != 1 or readme.count(PROGRESS_END) != 1:
        errors.append("README must contain exactly one SWIR-PYPI-PROGRESS marker pair")
    elif EXPECTED_BLOCK not in readme:
        errors.append("README PyPI progress block must be the deterministic 100.0% ASCII block")

    if "Latest public stable release:** **SwirEngine 2.1.0" not in readme:
        errors.append("README must identify SwirEngine 2.1.0 as the public stable release")
    if 'swirengine==2.1.0' not in readme:
        errors.append("README must advertise the exact 2.1.0 PyPI install after publication")
    if "Latest public stable release:** **SwirEngine 2.0.0" in readme:
        errors.append("README still claims 2.0.0 is the latest public stable release")

    block = ""
    if PROGRESS_START in readme and PROGRESS_END in readme:
        block = readme.split(PROGRESS_START, 1)[1].split(PROGRESS_END, 1)[0]
    if ".svg" in block or "<img" in block or "![" in block:
        errors.append("SVG/image progress is forbidden inside the PyPI ASCII progress block")

    if "Current verified progress: 10/10 milestones = 100.0%." not in roadmap:
        errors.append("ROADMAP_2_1.md must remain accepted at 10/10 = 100.0%")

    if not notes.startswith("# SwirEngine 2.1.0 Release Notes"):
        errors.append("RELEASE_NOTES_2_1.md must be final 2.1.0 release notes")
    if "NOT PUBLISHED" in notes or "candidate preparation only" in notes:
        errors.append("release notes still contain candidate-only publication wording")
    if 'swirengine==2.1.0' not in notes:
        errors.append("release notes must include the exact 2.1.0 install command")

    required_release_fragments = (
        "RELEASE_VERSION: 2.1.0",
        "RELEASE_TAG: v2.1.0",
        "environment: pypi",
        "id-token: write",
        "gh release create",
        "pypa/gh-action-pypi-publish@release/v1",
        "release_evidence_2_1.py",
    )
    for fragment in required_release_fragments:
        if fragment not in release:
            errors.append(f"release workflow missing required fragment: {fragment}")

    if "PYPI_API_TOKEN" in release or "TWINE_PASSWORD" in release:
        errors.append("release workflow must use trusted publishing, not stored PyPI tokens")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = verify(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("SwirEngine 2.1 publication contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
