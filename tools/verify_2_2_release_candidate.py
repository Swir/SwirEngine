from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - CPython 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "Swir/SwirEngine"
EXPECTED_VERSION = "2.2.0"
PUBLIC_STABLE_VERSION = "2.1.0"
EXPECTED_PYTHON_RANGE = ">=3.10,<3.15"
EXPECTED_COMPLETED = 9
EXPECTED_TOTAL = 10
EXPECTED_WORKFLOW_COUNT = 47
PACKAGE_DESCRIPTION = "PYPI_DESCRIPTION_2_2.md"
WORKFLOW = ".github/workflows/release-candidate-2.2.yml"
WORKFLOW_NAME = "SwirEngine 2.2 Release Candidate"
MANIFEST = ".github/release-gates/2.2-required-workflows.json"
EVIDENCE_TOOL = "tools/candidate_evidence_2_2.py"
MARKER_ROOT = ".release/publish-2.2.0"

MILESTONE_RE = re.compile(
    r"^- \[(?P<state>[ xX])\] \*\*(?P<number>\d+)\.",
    re.MULTILINE,
)
SUMMARY_RE = re.compile(
    r"Current verified progress:\s*(?P<done>\d+)/(?P<total>\d+)\s+milestones\s*=\s*"
    r"(?P<percent>\d+(?:\.\d+)?)%\."
)
M10_OPEN_RE = re.compile(
    r"^- \[ \] \*\*10\. Production acceptance and 2\.2 release readiness\.\*\*",
    re.MULTILINE,
)
RUNTIME_VERSION_RE = re.compile(
    r'^__version__\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
    re.MULTILINE,
)

REQUIRED_FILES = (
    "pyproject.toml",
    "src/swirengine/__init__.py",
    "README.md",
    "ROADMAP_2_2.md",
    "RELEASE_NOTES_2_2.md",
    PACKAGE_DESCRIPTION,
    "docs/MIGRATING_TO_2_2.md",
    "docs/RELEASE_GATE_2_2.md",
    WORKFLOW,
    MANIFEST,
    EVIDENCE_TOOL,
)

REQUIRED_WORKFLOW_PATHS = (
    "README.md",
    "ROADMAP_2_2.md",
    "RELEASE_NOTES_2_2.md",
    PACKAGE_DESCRIPTION,
    "pyproject.toml",
    "docs/MIGRATING_TO_2_2.md",
    "docs/RELEASE_GATE_2_2.md",
    MANIFEST,
    WORKFLOW,
    "tools/verify_2_2_release_candidate.py",
    EVIDENCE_TOOL,
    "tests/test_verify_2_2_release_candidate.py",
    "tests/test_candidate_evidence_2_2.py",
    "tools/verify_sdist_identity_2_2.py",
    "tests/test_sdist_identity_2_2.py",
    "tests/test_vendored_wheel.py",
    "src/**",
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
    "write-all",
    "actions/github-script",
    "refs/tags/v2.2.0",
    MARKER_ROOT,
    "skip-existing",
    "--clobber",
)


@dataclass(frozen=True, slots=True)
class RoadmapState:
    completed: int
    total: int
    percent: float


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _normalized_words(value: str) -> str:
    return " ".join(value.split()).casefold()


def parse_roadmap(text: str) -> RoadmapState:
    matches = list(MILESTONE_RE.finditer(text))
    numbers = [int(match.group("number")) for match in matches]
    if numbers != list(range(1, EXPECTED_TOTAL + 1)):
        raise ValueError("2.2 roadmap must contain exactly ten contiguous milestones")
    completed = sum(match.group("state").casefold() == "x" for match in matches)
    total = len(matches)
    percent = completed / total * 100.0
    summary = SUMMARY_RE.search(text)
    if summary is None:
        raise ValueError("2.2 roadmap is missing the verified progress summary")
    if int(summary.group("done")) != completed or int(summary.group("total")) != total:
        raise ValueError("2.2 roadmap summary disagrees with its milestone checklist")
    if abs(float(summary.group("percent")) - percent) > 0.05:
        raise ValueError("2.2 roadmap percentage disagrees with its milestone checklist")
    if completed != EXPECTED_COMPLETED or total != EXPECTED_TOTAL:
        raise ValueError("Phase B candidate must remain exactly 9/10 until Phase E")
    if len(M10_OPEN_RE.findall(text)) != 1:
        raise ValueError("Milestone 10 must remain open exactly once during Phase B")
    return RoadmapState(completed=completed, total=total, percent=percent)


def _workflow_mapping(text: str) -> Mapping[str, Any]:
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    if not isinstance(parsed, Mapping):
        raise TypeError("candidate workflow must be a YAML mapping")
    return parsed


def validate_candidate_workflow(text: str) -> list[str]:
    errors: list[str] = []
    try:
        workflow = _workflow_mapping(text)
    except yaml.YAMLError as exc:
        return [f"candidate workflow YAML is invalid: {exc}"]
    except TypeError as exc:
        return [str(exc)]

    if workflow.get("name") != WORKFLOW_NAME:
        errors.append(f"candidate workflow name must be exactly {WORKFLOW_NAME!r}")

    triggers = workflow.get("on")
    if not isinstance(triggers, Mapping) or set(triggers) != {"pull_request"}:
        errors.append("candidate workflow trigger must be pull_request only")
        pull_request: Mapping[str, Any] = {}
    else:
        candidate = triggers.get("pull_request")
        pull_request = candidate if isinstance(candidate, Mapping) else {}
    if pull_request.get("branches") != ["main"]:
        errors.append("candidate workflow pull_request base branch must be exactly main")
    paths = pull_request.get("paths")
    if not isinstance(paths, list):
        errors.append("candidate workflow must declare explicit pull_request paths")
    else:
        for path in REQUIRED_WORKFLOW_PATHS:
            if path not in paths:
                errors.append(f"candidate workflow path filter is missing: {path}")

    if workflow.get("permissions") != {"contents": "read"}:
        errors.append("candidate workflow must declare only top-level contents: read")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, Mapping):
        errors.append("candidate workflow must contain a jobs mapping")
    else:
        for job_name, job in jobs.items():
            if (
                isinstance(job, Mapping)
                and "permissions" in job
                and job.get("permissions") != {"contents": "read"}
            ):
                errors.append(
                    f"candidate workflow job permissions must remain contents: read: {job_name}"
                )

    required_fragments = (
        "github.event.pull_request.head.sha",
        "github.event.pull_request.head.ref",
        "github.event.pull_request.head.repo.full_name",
        "github.event.pull_request.base.ref",
        "github.repository",
        "Swir/SwirEngine",
        "release/2.2.0-candidate",
        "persist-credentials: false",
        "$GITHUB_EVENT_PATH",
        "git rev-parse HEAD",
        "python tools/verify_2_2_release_candidate.py",
        "python tools/verify_2_2_release_readiness.py",
        "python tools/verify_required_workflows_2_2.py",
        "python tools/verify_distribution_audit_data_2_2.py",
        "python tools/candidate_evidence_2_2.py generate",
        "python tools/candidate_evidence_2_2.py verify",
        "--source-sha",
        "--workflow-manifest .github/release-gates/2.2-required-workflows.json",
        "--expected-version 2.2.0",
        "--wheel-only",
        "candidate-provenance.json",
        "retention-days: 7",
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
        '"3.10"',
        '"3.11"',
        '"3.12"',
        '"3.13"',
        '"3.14"',
    )
    for fragment in required_fragments:
        if fragment not in text:
            errors.append(f"candidate workflow is missing required contract: {fragment}")

    folded = text.casefold()
    for fragment in FORBIDDEN_WORKFLOW_FRAGMENTS:
        if fragment in folded:
            errors.append(f"candidate workflow contains forbidden publishing capability: {fragment}")
    return errors


def _manifest_errors(text: str) -> list[str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"required-workflow manifest is invalid JSON: {exc}"]
    if not isinstance(payload, Mapping):
        return ["required-workflow manifest must be a JSON object"]
    errors: list[str] = []
    if set(payload) != {"schema_version", "repository", "required_workflows"}:
        errors.append("required-workflow manifest has unexpected top-level fields")
    if payload.get("schema_version") != 1:
        errors.append("required-workflow manifest schema_version must be 1")
    if payload.get("repository") != EXPECTED_REPOSITORY:
        errors.append(f"required-workflow manifest repository must be {EXPECTED_REPOSITORY}")
    entries = payload.get("required_workflows")
    if not isinstance(entries, list):
        errors.append("required-workflow manifest must contain a workflow list")
        return errors
    if len(entries) != EXPECTED_WORKFLOW_COUNT:
        errors.append(
            f"required-workflow manifest must contain exactly {EXPECTED_WORKFLOW_COUNT} workflows"
        )
    identities: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {"path", "name"}:
            errors.append("every required-workflow entry must contain only path and name")
            continue
        path = entry.get("path")
        name = entry.get("name")
        if not isinstance(path, str) or not path or not isinstance(name, str) or not name:
            errors.append("required-workflow path and name must be non-empty strings")
            continue
        identities.append((path, name))
    paths = [path for path, _ in identities]
    names = [name for _, name in identities]
    if len(set(paths)) != len(paths):
        errors.append("required-workflow manifest contains duplicate paths")
    if len(set(names)) != len(names):
        errors.append("required-workflow manifest contains duplicate names")
    if (WORKFLOW, WORKFLOW_NAME) not in identities:
        errors.append("required-workflow manifest does not require the Phase B candidate workflow")
    return errors


def _candidate_marker_exists(root: Path) -> bool:
    try:
        roots = [
            path
            for path in root.iterdir()
            if path.name.rstrip(" .").casefold() == ".release"
        ]
    except OSError:
        return True
    for release_root in roots:
        if not release_root.is_dir():
            return True
        try:
            children = tuple(release_root.iterdir())
        except OSError:
            return True
        if any(
            child.name.rstrip(" .").casefold() == "publish-2.2.0"
            for child in children
        ):
            return True
    return False


def check_release_candidate(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    missing = [
        relative
        for relative in REQUIRED_FILES
        if (root / relative).is_symlink() or not (root / relative).is_file()
    ]
    if missing:
        return [f"missing required Phase B file: {relative}" for relative in missing]

    try:
        document = tomllib.loads(_read(root, "pyproject.toml"))
        project = document["project"]
    except (KeyError, tomllib.TOMLDecodeError) as exc:
        return [f"invalid pyproject project metadata: {exc}"]
    if not isinstance(project, Mapping):
        return ["pyproject project metadata must be a table"]
    if project.get("version") != EXPECTED_VERSION:
        errors.append(f"pyproject project.version must be exactly {EXPECTED_VERSION}")
    if project.get("readme") != PACKAGE_DESCRIPTION:
        errors.append(f"pyproject project.readme must be exactly {PACKAGE_DESCRIPTION}")
    if project.get("requires-python") != EXPECTED_PYTHON_RANGE:
        errors.append(f"pyproject requires-python must remain {EXPECTED_PYTHON_RANGE}")
    classifiers = project.get("classifiers")
    if not isinstance(classifiers, list):
        errors.append("pyproject classifiers must be a list")
    else:
        for minor in range(10, 15):
            classifier = f"Programming Language :: Python :: 3.{minor}"
            if classifier not in classifiers:
                errors.append(f"pyproject classifier is missing: {classifier}")
    urls = project.get("urls")
    if not isinstance(urls, Mapping):
        errors.append("pyproject project.urls must be a table")
    else:
        if not str(urls.get("Roadmap", "")).endswith("/ROADMAP_2_2.md"):
            errors.append("primary project Roadmap URL must point to ROADMAP_2_2.md")
        if not str(urls.get("2.2 Roadmap", "")).endswith("/ROADMAP_2_2.md"):
            errors.append("project metadata must expose an explicit 2.2 Roadmap URL")
        if not str(urls.get("2.1 Roadmap", "")).endswith("/ROADMAP_2_1.md"):
            errors.append("project metadata must preserve the historical 2.1 Roadmap URL")
    try:
        exclusions = document["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    except KeyError:
        exclusions = []
    if not isinstance(exclusions, list) or not {"/.release", "/release-evidence"}.issubset(
        set(exclusions)
    ):
        errors.append("sdist must exclude both /.release and /release-evidence")

    runtime_matches = list(RUNTIME_VERSION_RE.finditer(_read(root, "src/swirengine/__init__.py")))
    if len(runtime_matches) != 1 or runtime_matches[0].group("version") != EXPECTED_VERSION:
        errors.append(f"runtime must declare exactly one __version__ = {EXPECTED_VERSION!r}")

    try:
        parse_roadmap(_read(root, "ROADMAP_2_2.md"))
    except ValueError as exc:
        errors.append(str(exc))

    readme = _read(root, "README.md")
    readme_words = _normalized_words(readme)
    for fragment in (
        "swirengine 2.2.0",
        "bound non-publishing candidate",
        "**latest public stable release:** **swirengine 2.1.0**",
        "swirengine==2.1.0",
    ):
        if fragment not in readme_words:
            errors.append(f"README candidate/public-stable contract is missing: {fragment}")
    for fragment in ("swirengine==2.2.0", "swirengine[audio]==2.2.0"):
        if fragment in readme_words:
            errors.append(f"README must not advertise an unpublished public install: {fragment}")

    notes = _read(root, "RELEASE_NOTES_2_2.md")
    notes_words = _normalized_words(notes)
    if not notes.startswith("# SwirEngine 2.2.0 Release Notes\n"):
        errors.append("RELEASE_NOTES_2_2.md must use the exact 2.2.0 release-notes title")
    for fragment in ("candidate", "provenance", "tag", "pypi"):
        if fragment not in notes_words:
            errors.append(f"release notes are missing publication-ready provenance text: {fragment}")
    for fragment in (
        "not published",
        "non-publishing",
        "candidate preparation only",
        "latest public stable release",
        "public stable release remains",
    ):
        if fragment in notes_words:
            errors.append(f"release notes contain transient candidate wording: {fragment}")

    package_description = _read(root, PACKAGE_DESCRIPTION)
    description_words = _normalized_words(package_description)
    if "swirengine 2.2.0" not in description_words:
        errors.append(f"{PACKAGE_DESCRIPTION} must identify SwirEngine 2.2.0")
    for fragment in (
        "not published",
        "bound non-publishing candidate",
        "candidate preparation only",
        "latest public stable release",
        "swirengine==2.1.0",
        "source development only",
    ):
        if fragment in description_words:
            errors.append(f"{PACKAGE_DESCRIPTION} contains transient repository status: {fragment}")

    migration = _normalized_words(_read(root, "docs/MIGRATING_TO_2_2.md"))
    if "phase b" not in migration or "bound non-publishing candidate" not in migration:
        errors.append("migration guide must document the bound non-publishing Phase B candidate")
    gate = _normalized_words(_read(root, "docs/RELEASE_GATE_2_2.md"))
    if "phase b" not in gate or "bound non-publishing candidate" not in gate:
        errors.append("release gate must preserve the bound non-publishing Phase B boundary")

    errors.extend(validate_candidate_workflow(_read(root, WORKFLOW)))
    errors.extend(_manifest_errors(_read(root, MANIFEST)))

    if _candidate_marker_exists(root):
        errors.append(f"Phase B source must not contain {MARKER_ROOT} or a Windows alias")
    return errors


def main() -> int:
    errors = check_release_candidate()
    if errors:
        print("SwirEngine 2.2 release-candidate verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SwirEngine 2.2 release-candidate verification passed (bound, non-publishing).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
