from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - CPython 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "Swir/SwirEngine"
EXPECTED_VERSION = "2.2.1"
PREVIOUS_PUBLIC_VERSION = "2.2.0"
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
PACKAGE_DESCRIPTION = "PYPI_DESCRIPTION_2_2_1.md"
RELEASE_NOTES = "RELEASE_NOTES_2_2_1.md"
WORKFLOW = ".github/workflows/release-candidate-2.2.1.yml"
WORKFLOW_NAME = "SwirEngine 2.2.1 Release Candidate"
MANIFEST = ".github/release-gates/2.2.1-required-workflows.json"
HISTORICAL_MANIFEST = ".github/release-gates/2.2-required-workflows.json"
MARKER_ROOT = ".release/publish-2.2.1"
EXPECTED_WORKFLOW_COUNT = 48
NEW_WORKFLOW_ENTRY = {"path": WORKFLOW, "name": WORKFLOW_NAME}

IMMUTABLE_2_2_0_DIGESTS = {
    "PYPI_DESCRIPTION_2_2.md": (
        "2c6a0bbe870b360c14fd4ae9d28f4957a2168912bd5072266ea62266b257a126"
    ),
    "RELEASE_NOTES_2_2.md": (
        "1350ef99dbb1d6ba6b9d516024b1d30ebaa0ce232d417e46a0ed3a700afae572"
    ),
    HISTORICAL_MANIFEST: (
        "4b765c20736147881e99bc2a9414265815fbda2013bd20fc32d27be6f189e17a"
    ),
    "release-evidence/2.2.0/manifest.json": (
        "5647da822fb27063cd51e1e4c1e7abd89dc5dac459617f1fb725b3ef554dad0c"
    ),
    "tools/verify_public_release_2_2.py": (
        "bf7d4bb733d8d637e990bb9b049287f0ba225a714481bd70126c3647dd2b0c32"
    ),
    "tools/verify_publication_chain_2_2.py": (
        "4c512acc3d82d1d6b3df826dbed71fe9bdbe8e2c604bcf2cda90505c4c56b150"
    ),
    "tools/candidate_evidence_2_2.py": (
        "0abf14e42051152fbfae2f8754eab34a757913df9f6370ee0d80f6cc20fd5e97"
    ),
    "tools/release_evidence_2_2.py": (
        "fc7513d6d639792768e1cb8ef03e8800fd7de5243850091f507689234125c611"
    ),
    "tools/reconcile_release_2_2.py": (
        "cdcdea836580f1a0b08f4e5a9404be7c81342064994e7176711dd6d7adf8369f"
    ),
    ".github/workflows/post-release-2.2.yml": (
        "ba6a75cb82081205624cb4ba6f1b5caefa19a26f4ebd92f48120298183e79c4c"
    ),
    ".github/workflows/publication-gate-2.2.yml": (
        "5aec66be17ee176514cf3f5acc0d4569d7fec8a121ded17cfd4fc8c1336aebac"
    ),
}

REQUIRED_FILES = (
    "pyproject.toml",
    "src/swirengine/__init__.py",
    "README.md",
    "ROADMAP_2_2.md",
    PACKAGE_DESCRIPTION,
    RELEASE_NOTES,
    WORKFLOW,
    MANIFEST,
    HISTORICAL_MANIFEST,
    "release-evidence/2.2.0/manifest.json",
    "tools/verify_2_2_1_release_candidate.py",
    "tools/verify_publication_chain_2_2_1.py",
    "tools/candidate_evidence_2_2_1.py",
    "tools/release_evidence_2_2_1.py",
    "tools/reconcile_release_2_2_1.py",
)

REQUIRED_WORKFLOW_PATHS = (
    "pyproject.toml",
    "src/**",
    PACKAGE_DESCRIPTION,
    RELEASE_NOTES,
    MANIFEST,
    WORKFLOW,
    "tools/**",
    "tests/**",
)

FORBIDDEN_WORKFLOW_FRAGMENTS = (
    "contents: write",
    "id-token: write",
    "packages: write",
    "pull-requests: write",
    "environment: pypi",
    "pypa/gh-action-pypi-publish",
    "twine upload",
    "gh release create",
    "git tag",
    "git push",
    "workflow_dispatch",
    "refs/tags/v2.2.1",
    MARKER_ROOT,
    "skip-existing",
    "--clobber",
)

RUNTIME_VERSION_RE = re.compile(
    r'^__version__\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
    re.MULTILINE,
)
MILESTONE_RE = re.compile(r"^- \[[xX]\] \*\*(?P<number>\d+)\.", re.MULTILINE)
RELATIVE_LINK_RE = re.compile(r"]\((?!https://|#)[^)]+\)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _workflow_mapping(text: str) -> Mapping[str, Any]:
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    if not isinstance(parsed, Mapping):
        raise TypeError("candidate workflow must be a YAML mapping")
    return parsed


def _uses_values(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "uses" and isinstance(child, str):
                found.append(child)
            found.extend(_uses_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_uses_values(child))
    return found


def validate_candidate_workflow(text: str) -> list[str]:
    errors: list[str] = []
    try:
        workflow = _workflow_mapping(text)
    except (yaml.YAMLError, TypeError) as exc:
        return [f"candidate workflow is invalid: {exc}"]
    if workflow.get("name") != WORKFLOW_NAME:
        errors.append(f"candidate workflow name must be exactly {WORKFLOW_NAME!r}")
    triggers = workflow.get("on")
    if not isinstance(triggers, Mapping) or set(triggers) != {"pull_request"}:
        errors.append("candidate workflow trigger must be pull_request only")
        pull_request: Mapping[str, Any] = {}
    else:
        value = triggers.get("pull_request")
        pull_request = value if isinstance(value, Mapping) else {}
    if pull_request.get("branches") != ["main"]:
        errors.append("candidate workflow base branch must be exactly main")
    paths = pull_request.get("paths")
    if not isinstance(paths, list):
        errors.append("candidate workflow must declare explicit pull_request paths")
    else:
        for path in REQUIRED_WORKFLOW_PATHS:
            if path not in paths:
                errors.append(f"candidate workflow path filter is missing: {path}")
    if workflow.get("permissions") != {"contents": "read"}:
        errors.append("candidate workflow permissions must be exactly contents: read")
    folded = text.casefold()
    for fragment in FORBIDDEN_WORKFLOW_FRAGMENTS:
        if fragment.casefold() in folded:
            errors.append(f"candidate workflow contains forbidden publishing fragment: {fragment}")
    required_fragments = (
        "release/2.2.1",
        "github.event.pull_request.head.sha",
        "persist-credentials: false",
        "fetch-depth: 0",
        "python tools/verify_2_2_1_release_candidate.py",
        "python tools/candidate_evidence_2_2_1.py",
        "--expected-version 2.2.1",
        "python -m pytest",
        "python -m ruff check",
        "python -m compileall",
        "python -m build",
        "twine check",
    )
    for fragment in required_fragments:
        if fragment not in text:
            errors.append(f"candidate workflow is missing required fragment: {fragment}")
    for uses in _uses_values(workflow):
        revision = uses.rpartition("@")[2]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            errors.append(f"candidate workflow action must be pinned to a commit SHA: {uses}")
    return errors


def _manifest_entries(payload: object, *, subject: str) -> list[dict[str, str]]:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{subject} must be an object")
    if set(payload) != {"schema_version", "repository", "required_workflows"}:
        raise ValueError(f"{subject} has an unexpected schema")
    if payload.get("schema_version") != 1 or payload.get("repository") != EXPECTED_REPOSITORY:
        raise ValueError(f"{subject} identity is invalid")
    values = payload.get("required_workflows")
    if not isinstance(values, list):
        raise TypeError(f"{subject} required_workflows must be an array")
    entries: list[dict[str, str]] = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {"path", "name"}:
            raise ValueError(f"{subject} entry {index} has an invalid schema")
        path = value.get("path")
        name = value.get("name")
        if not isinstance(path, str) or not isinstance(name, str) or not path or not name:
            raise ValueError(f"{subject} entry {index} has an invalid identity")
        entries.append({"path": path, "name": name})
    if len({item["path"] for item in entries}) != len(entries):
        raise ValueError(f"{subject} contains duplicate paths")
    if len({item["name"] for item in entries}) != len(entries):
        raise ValueError(f"{subject} contains duplicate names")
    return entries


def validate_manifest_transition(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        historical = json.loads(_read(root, HISTORICAL_MANIFEST))
        patch = json.loads(_read(root, MANIFEST))
        old_entries = _manifest_entries(historical, subject="2.2.0 manifest")
        new_entries = _manifest_entries(patch, subject="2.2.1 manifest")
        if len(old_entries) != 47:
            errors.append("historical manifest must preserve exactly 47 workflows")
        if len(new_entries) != EXPECTED_WORKFLOW_COUNT:
            errors.append(f"2.2.1 manifest must contain exactly {EXPECTED_WORKFLOW_COUNT} workflows")
        if new_entries[: len(old_entries)] != old_entries:
            errors.append("2.2.1 manifest must preserve all historical entries in exact order")
        if not new_entries or new_entries[-1] != NEW_WORKFLOW_ENTRY:
            errors.append("2.2.1 manifest must append only the exact candidate workflow")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"required-workflow manifest is invalid: {exc}")
    return errors


def _validate_description(text: str) -> list[str]:
    errors: list[str] = []
    folded = " ".join(text.split()).casefold()
    if not text.startswith("# SwirEngine 2.2.1\n"):
        errors.append(f"{PACKAGE_DESCRIPTION} must use the exact 2.2.1 title")
    if len(text) < 3000 or text.count("\n## ") < 6:
        errors.append(f"{PACKAGE_DESCRIPTION} must be a detailed multi-section package guide")
    for fragment in (
        "swirengine==2.2.1",
        "swirengine[audio]==2.2.1",
        "2d",
        "3d",
        "multiplayer",
        "swireditor",
        "python 3.10",
        "python 3.14",
        "https://github.com/swir/swirengine",
    ):
        if fragment not in folded:
            errors.append(f"{PACKAGE_DESCRIPTION} is missing required detail: {fragment}")
    if "not published" in folded or "latest public stable" in folded:
        errors.append(f"{PACKAGE_DESCRIPTION} must remain publication-ready and time-neutral")
    if RELATIVE_LINK_RE.search(text):
        errors.append(f"{PACKAGE_DESCRIPTION} must use PyPI-safe absolute or anchor links")
    return errors


def _validate_notes(text: str) -> list[str]:
    errors: list[str] = []
    folded = " ".join(text.split()).casefold()
    if not text.startswith("# SwirEngine 2.2.1 Release Notes\n"):
        errors.append(f"{RELEASE_NOTES} must use the exact 2.2.1 title")
    for fragment in (
        "metadata-only maintenance release",
        "no public api or runtime behavior changes",
        PACKAGE_DESCRIPTION.casefold(),
    ):
        if fragment not in folded:
            errors.append(f"{RELEASE_NOTES} is missing required statement: {fragment}")
    if "not published" in folded:
        errors.append(f"{RELEASE_NOTES} must be publication-ready")
    return errors


def _forbidden_marker_root(root: Path) -> str | None:
    try:
        release_roots = tuple(
            child
            for child in root.iterdir()
            if unicodedata.normalize("NFC", child.name).rstrip(" .").casefold() == ".release"
        )
    except OSError:
        return "<unreadable repository root>"
    for release_root in release_roots:
        if release_root.is_symlink() or not release_root.is_dir():
            return release_root.name
        try:
            children = tuple(release_root.iterdir())
        except OSError:
            return f"{release_root.name}/<unreadable>"
        for child in children:
            normalized = unicodedata.normalize("NFC", child.name).rstrip(" .").casefold()
            if normalized == "publish-2.2.1":
                return f"{release_root.name}/{child.name}"
    return None


def check_release_candidate(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"required 2.2.1 candidate file is missing or unsafe: {relative}")
    if errors:
        return errors
    for relative, expected in IMMUTABLE_2_2_0_DIGESTS.items():
        actual = _sha256(root / relative)
        if actual != expected:
            errors.append(f"immutable 2.2.0 file changed: {relative} ({actual} != {expected})")
    try:
        project = tomllib.loads(_read(root, "pyproject.toml"))["project"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"pyproject metadata is invalid: {exc}")
        project = {}
    if project.get("name") != "swirengine":
        errors.append("pyproject project.name must be exactly swirengine")
    if project.get("version") != EXPECTED_VERSION:
        errors.append(f"pyproject project.version must be exactly {EXPECTED_VERSION}")
    if project.get("readme") != PACKAGE_DESCRIPTION:
        errors.append(f"pyproject project.readme must be exactly {PACKAGE_DESCRIPTION}")
    if project.get("requires-python") != EXPECTED_PYTHON_RANGE:
        errors.append(f"pyproject requires-python must remain {EXPECTED_PYTHON_RANGE}")
    runtime_versions = RUNTIME_VERSION_RE.findall(_read(root, "src/swirengine/__init__.py"))
    if runtime_versions != [EXPECTED_VERSION]:
        errors.append(f"runtime must declare exactly one __version__ = {EXPECTED_VERSION!r}")
    roadmap = _read(root, "ROADMAP_2_2.md")
    numbers = [int(match.group("number")) for match in MILESTONE_RE.finditer(roadmap)]
    if numbers != list(range(1, 11)) or "10/10 milestones = 100.0%." not in roadmap:
        errors.append("2.2.1 candidate must preserve the accepted 2.2 roadmap at 10/10")
    readme = _read(root, "README.md")
    if "**Latest public stable release:** **SwirEngine 2.2.0**" not in readme:
        errors.append("pre-publication README must keep 2.2.0 as the public stable release")
    if '"swirengine==2.2.0"' not in readme or '"swirengine==2.2.1"' in readme:
        errors.append("pre-publication README must install 2.2.0 and must not advertise 2.2.1")
    errors.extend(_validate_description(_read(root, PACKAGE_DESCRIPTION)))
    errors.extend(_validate_notes(_read(root, RELEASE_NOTES)))
    errors.extend(validate_manifest_transition(root))
    errors.extend(validate_candidate_workflow(_read(root, WORKFLOW)))
    marker = _forbidden_marker_root(root)
    if marker is not None:
        errors.append(f"candidate source must not contain publication control root: {marker}")
    return errors


def main() -> int:
    errors = check_release_candidate(ROOT)
    if errors:
        print("SwirEngine 2.2.1 release candidate verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SwirEngine 2.2.1 release candidate verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
