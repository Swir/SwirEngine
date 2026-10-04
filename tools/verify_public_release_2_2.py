from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from tools.reconcile_release_2_2 import (
        ReleaseReconciliationError,
        ReleaseSnapshot,
        load_expected_release,
        reconcile_release,
    )
    from tools.release_evidence_2_2 import ReleaseEvidenceError, verify_evidence
    from tools.verify_publication_chain_2_2 import PublicationChainError, verify_chain
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from reconcile_release_2_2 import (
        ReleaseReconciliationError,
        ReleaseSnapshot,
        load_expected_release,
        reconcile_release,
    )
    from release_evidence_2_2 import ReleaseEvidenceError, verify_evidence
    from verify_publication_chain_2_2 import PublicationChainError, verify_chain

SCHEMA = "swirengine-public-release-evidence-v4"
REPOSITORY = "Swir/SwirEngine"
PACKAGE = "swirengine"
VERSION = "2.2.0"
TAG = "v2.2.0"
EXPECTED_REQUIRES_PYTHON = frozenset({">=3.10", "<3.15"})
DEFAULT_EVIDENCE = Path("release-evidence/2.2.0/manifest.json")
WORKFLOW_MANIFEST = PurePosixPath(".github/release-gates/2.2-required-workflows.json")
RELEASE_NOTES = Path("RELEASE_NOTES_2_2.md")
PYPI_DESCRIPTION = Path("PYPI_DESCRIPTION_2_2.md")
POST_RELEASE_WORKFLOW = Path(".github/workflows/post-release-2.2.yml")
RETIRED_CANDIDATE_WORKFLOW = Path(".github/workflows/release-candidate-2.2.yml")

CANDIDATE_SOURCE_COMMIT = "efd5d2b5c26941d49599cd925bb1f8c35b844c3f"
CANDIDATE_MARKER_COMMIT = "48ca4b55b9707845796451136002a4c6568ac231"
PUBLICATION_COMMIT = "2f150ba6f3fd1e1fd121a8884298e616186e267b"
PUBLICATION_REQUIRED_WORKFLOWS_SHA256 = (
    "9ca3c9f2fd42e7ac410d571f6847c22e94e04ce522322b83f07e48e3070b0f49"
)
PHASE_E_REQUIRED_WORKFLOWS_SHA256 = (
    "4b765c20736147881e99bc2a9414265815fbda2013bd20fc32d27be6f189e17a"
)
LOGICAL_SDIST_SHA256 = "e0a48491ee53820b0a5af370e960879d6d359a361014242dad528322351afd75"
RELEASE_NOTES_SHA256 = "1350ef99dbb1d6ba6b9d516024b1d30ebaa0ce232d417e46a0ed3a700afae572"
PYPI_DESCRIPTION_SHA256 = "2c6a0bbe870b360c14fd4ae9d28f4957a2168912bd5072266ea62266b257a126"
RELEASE_RUN_ID = 37175535837
RELEASE_RUN_ATTEMPT = 1
TRUSTED_WORKFLOW_COMMIT = "8cfe640b216c06e5423821615f97828e43b917c6"

EXPECTED_RELEASE_ASSETS = (
    {
        "name": "SHA256SUMS",
        "sha256": "6473a712f90b342171ad5e1b30744d0cec5447b2a087be25d910a317b48cb3c5",
        "size": 299,
    },
    {
        "name": "release-provenance.json",
        "sha256": "2fbe6065bcfbe1c99284eae263f511bb4a0e0064b105805a6e7e1750545cc445",
        "size": 1064,
    },
    {
        "name": "swirengine-2.2.0-cp314-cp314-win_amd64.whl",
        "sha256": "1261932138e183773f3131ca7972d442e667e1d56c944ed8d18f3fc023f0ac8d",
        "size": 945574,
    },
    {
        "name": "swirengine-2.2.0-py3-none-any.whl",
        "sha256": "a16b47d9376e4fcf570ba91ce03545c62127999a61e6c60751a836f609bf4646",
        "size": 827421,
    },
    {
        "name": "swirengine-2.2.0.tar.gz",
        "sha256": "9f2048d8d5332f449a90d41164b1d19521f2c5802a0b40b5d3d9d0370cc37053",
        "size": 2884911,
    },
)
EXPECTED_DISTRIBUTION_NAMES = frozenset(
    item["name"]
    for item in EXPECTED_RELEASE_ASSETS
    if str(item["name"]).endswith((".whl", ".tar.gz"))
)
EXPECTED_SUCCESSFUL_JOBS = (
    {"id": 111357683135, "name": "Fresh-read and verify exact PyPI files"},
    {"id": 111357598636, "name": "Fresh-read and verify immutable GitHub Release"},
    {
        "id": 111357451691,
        "name": "Generate provenance and take initial public-state snapshot",
    },
    {
        "id": 111357703738,
        "name": "Public PyPI verify / macos-latest / Python 3.13",
    },
    {
        "id": 111357703757,
        "name": "Public PyPI verify / ubuntu-latest / Python 3.13",
    },
    {
        "id": 111357703747,
        "name": "Public PyPI verify / windows-latest / Python 3.14",
    },
    {"id": 111357256100, "name": "Verify immutable publication chain and trigger"},
    {
        "id": 111357784847,
        "name": "Verify immutable tag, release, package and evidence",
    },
)
EXPECTED_SKIPPED_JOBS = frozenset(
    {
        "Publish staged PyPI files through Trusted Publisher",
        "Publish the pre-reconciled immutable GitHub Release",
    }
)
OLD_WORKFLOW_ENTRY = {
    "path": ".github/workflows/release-candidate-2.2.yml",
    "name": "SwirEngine 2.2 Release Candidate",
}
NEW_WORKFLOW_ENTRY = {
    "path": ".github/workflows/post-release-2.2.yml",
    "name": "Post-release 2.2 Public Verification",
}

JsonMapping = Mapping[str, Any]
RequestJson = Callable[..., Any]
RequestBytes = Callable[..., bytes]


class PublicReleaseVerificationError(ValueError):
    """Raised when the final public 2.2 release evidence is not exact."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicReleaseVerificationError(message)


def _canonical_json(data: object) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_evidence() -> dict[str, Any]:
    """Return the single exact Phase E v4 evidence object."""

    return {
        "candidate_marker_commit": CANDIDATE_MARKER_COMMIT,
        "candidate_source_commit": CANDIDATE_SOURCE_COMMIT,
        "logical_sdist_sha256": LOGICAL_SDIST_SHA256,
        "package": PACKAGE,
        "phase_e_required_workflows_sha256": PHASE_E_REQUIRED_WORKFLOWS_SHA256,
        "publication_commit": PUBLICATION_COMMIT,
        "publication_required_workflows_sha256": (PUBLICATION_REQUIRED_WORKFLOWS_SHA256),
        "pypi_description_sha256": PYPI_DESCRIPTION_SHA256,
        "release_assets": [dict(item) for item in EXPECTED_RELEASE_ASSETS],
        "release_notes_sha256": RELEASE_NOTES_SHA256,
        "release_workflow": {
            "run_attempt": RELEASE_RUN_ATTEMPT,
            "run_id": RELEASE_RUN_ID,
            "successful_jobs": [dict(item) for item in EXPECTED_SUCCESSFUL_JOBS],
            "trusted_workflow_commit": TRUSTED_WORKFLOW_COMMIT,
        },
        "repository": REPOSITORY,
        "schema": SCHEMA,
        "tag": TAG,
        "version": VERSION,
    }


def _reject_json_constant(value: str) -> None:
    raise PublicReleaseVerificationError(f"non-finite JSON value is forbidden: {value}")


def load_evidence(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        parsed = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicReleaseVerificationError(f"cannot read public release evidence: {exc}") from exc
    _require(isinstance(parsed, dict), "public release evidence must be a JSON object")
    _require(raw == _canonical_json(parsed), "public release evidence is not canonical JSON")
    expected = expected_evidence()
    _require(
        raw == _canonical_json(expected),
        "public release evidence does not match the exact accepted Phase E v4 record",
    )
    return parsed


def _git_bytes(root: Path, *args: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise PublicReleaseVerificationError(f"git {' '.join(args)} failed{suffix}") from exc
    return completed.stdout


def _workflow_manifest(payload: object, *, source: str) -> list[dict[str, str]]:
    _require(isinstance(payload, Mapping), f"{source} workflow manifest must be an object")
    assert isinstance(payload, Mapping)
    _require(
        set(payload) == {"schema_version", "repository", "required_workflows"},
        f"{source} workflow manifest has an unexpected schema",
    )
    _require(payload.get("schema_version") == 1, f"{source} workflow schema is not v1")
    _require(payload.get("repository") == REPOSITORY, f"{source} workflow repository is wrong")
    workflows = payload.get("required_workflows")
    _require(isinstance(workflows, list), f"{source} required_workflows must be an array")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(workflows):
        _require(isinstance(item, Mapping), f"{source} workflow {index} must be an object")
        assert isinstance(item, Mapping)
        _require(
            set(item) == {"name", "path"},
            f"{source} workflow {index} has an unexpected schema",
        )
        name = item.get("name")
        path = item.get("path")
        _require(
            isinstance(name, str) and bool(name),
            f"{source} workflow {index} has no name",
        )
        _require(
            isinstance(path, str) and path.startswith(".github/workflows/"),
            f"{source} workflow {index} has an invalid path",
        )
        normalized.append({"path": path, "name": name})
    _require(len(normalized) == 47, f"{source} workflow manifest must contain 47 entries")
    _require(
        len({item["path"] for item in normalized}) == len(normalized),
        f"{source} workflow manifest contains duplicate paths",
    )
    _require(
        len({item["name"] for item in normalized}) == len(normalized),
        f"{source} workflow manifest contains duplicate names",
    )
    return normalized


def validate_required_workflow_transition(old_raw: bytes, new_raw: bytes) -> None:
    try:
        old_payload = json.loads(old_raw.decode("utf-8"), parse_constant=_reject_json_constant)
        new_payload = json.loads(new_raw.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicReleaseVerificationError(
            f"invalid required-workflow manifest JSON: {exc}"
        ) from exc
    old = _workflow_manifest(old_payload, source="publication")
    new = _workflow_manifest(new_payload, source="Phase E")
    _require(len(old) == len(new), "Phase E workflow manifest changed entry count")
    changed = [index for index, pair in enumerate(zip(old, new, strict=True)) if pair[0] != pair[1]]
    _require(changed == [19], "Phase E must replace exactly one same-position workflow entry")
    index = changed[0]
    _require(old[index] == OLD_WORKFLOW_ENTRY, "Phase E did not retire the exact candidate gate")
    _require(new[index] == NEW_WORKFLOW_ENTRY, "Phase E did not add the exact public verifier gate")


def verify_repository_evidence(root: Path, evidence: JsonMapping) -> bytes:
    root = root.resolve()
    _require((root / ".git").exists(), f"not a Git worktree: {root}")
    chain = verify_chain(root, str(evidence["publication_commit"]))
    _require(
        chain.candidate_source_sha == evidence["candidate_source_commit"],
        "publication chain candidate source differs from Phase E evidence",
    )
    _require(
        chain.candidate_marker_sha == evidence["candidate_marker_commit"],
        "publication chain candidate marker differs from Phase E evidence",
    )
    _require(
        chain.publication_sha == evidence["publication_commit"],
        "publication chain tip differs from Phase E evidence",
    )
    _require(
        chain.workflow_manifest_sha256 == evidence["publication_required_workflows_sha256"],
        "publication workflow digest differs from Phase E evidence",
    )

    old_raw = _git_bytes(
        root,
        "show",
        f"{CANDIDATE_SOURCE_COMMIT}:{WORKFLOW_MANIFEST.as_posix()}",
    )
    _require(
        _sha256(old_raw) == evidence["publication_required_workflows_sha256"],
        "candidate-source workflow manifest digest differs from evidence",
    )
    current_path = root / Path(WORKFLOW_MANIFEST.as_posix())
    _require(
        current_path.is_file() and not current_path.is_symlink(),
        "Phase E workflow manifest is missing or unsafe",
    )
    current_raw = current_path.read_bytes()
    _require(
        _sha256(current_raw) == evidence["phase_e_required_workflows_sha256"],
        "Phase E workflow manifest digest differs from evidence",
    )
    validate_required_workflow_transition(old_raw, current_raw)
    _require((root / POST_RELEASE_WORKFLOW).is_file(), "Phase E public workflow is missing")
    _require(
        not (root / RETIRED_CANDIDATE_WORKFLOW).exists(),
        "retired 2.2 candidate workflow is still present",
    )

    release_notes = root / RELEASE_NOTES
    pypi_description = root / PYPI_DESCRIPTION
    _require(release_notes.is_file(), "release notes are missing")
    _require(pypi_description.is_file(), "PyPI description is missing")
    _require(
        _sha256_path(release_notes) == evidence["release_notes_sha256"],
        "release notes digest differs from Phase E evidence",
    )
    _require(
        _sha256_path(pypi_description) == evidence["pypi_description_sha256"],
        "PyPI description digest differs from Phase E evidence",
    )
    return old_raw


def _require_mapping(value: object, *, source: str) -> JsonMapping:
    _require(isinstance(value, Mapping), f"{source} must be a JSON object")
    assert isinstance(value, Mapping)
    return value


def _request_bytes(
    url: str,
    *,
    token: str | None = None,
    accept: str = "application/octet-stream",
    attempts: int = 6,
) -> bytes:
    headers = {"Accept": accept, "User-Agent": "SwirEngine-2.2-public-release-verifier"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            if attempt + 1 == attempts:
                raise PublicReleaseVerificationError(f"request failed for {url}: {exc}") from exc
            time.sleep(min(2**attempt, 10))
    raise AssertionError("unreachable")


def _request_json(url: str, *, token: str | None = None, attempts: int = 6) -> Any:
    raw = _request_bytes(
        url,
        token=token,
        accept="application/vnd.github+json",
        attempts=attempts,
    )
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicReleaseVerificationError(f"invalid JSON from {url}: {exc}") from exc


def _exact_int(value: object, *, field: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{field} must be an integer",
    )
    return value


def validate_release_workflow(
    run_payload: object,
    jobs_payload: object,
    release_workflow: JsonMapping,
) -> None:
    run = _require_mapping(run_payload, source="release workflow run")
    expected_run_id = _exact_int(release_workflow.get("run_id"), field="evidence run_id")
    expected_attempt = _exact_int(release_workflow.get("run_attempt"), field="evidence run_attempt")
    expected_commit = release_workflow.get("trusted_workflow_commit")
    exact_run_fields = {
        "id": expected_run_id,
        "name": "Release",
        "path": ".github/workflows/release.yml",
        "event": "workflow_run",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": expected_attempt,
        "head_branch": "main",
        "head_sha": expected_commit,
    }
    for field, expected in exact_run_fields.items():
        _require(
            type(run.get(field)) is type(expected) and run.get(field) == expected,
            f"release workflow run has unexpected {field}: {run.get(field)!r}",
        )
    for field in ("repository", "head_repository"):
        repository = _require_mapping(run.get(field), source=f"release run {field}")
        _require(
            repository.get("full_name") == REPOSITORY,
            f"release workflow {field} is not {REPOSITORY}",
        )

    jobs_document = _require_mapping(jobs_payload, source="attempt-scoped jobs response")
    total_count = _exact_int(jobs_document.get("total_count"), field="jobs total_count")
    jobs = jobs_document.get("jobs")
    _require(isinstance(jobs, list), "attempt-scoped jobs response has no jobs array")
    assert isinstance(jobs, list)
    _require(total_count == len(jobs), "attempt-scoped jobs response is incomplete")
    _require(total_count <= 100, "attempt-scoped jobs response requires unsupported pagination")

    by_name: dict[str, JsonMapping] = {}
    ids: set[int] = set()
    skipped: set[str] = set()
    for index, value in enumerate(jobs):
        job = _require_mapping(value, source=f"release job {index}")
        job_id = _exact_int(job.get("id"), field=f"release job {index} id")
        name = job.get("name")
        _require(isinstance(name, str) and bool(name), f"release job {index} has no name")
        assert isinstance(name, str)
        _require("${{" not in name, f"unexpanded matrix placeholder job is forbidden: {name}")
        _require(job_id not in ids, f"duplicate release job id: {job_id}")
        _require(name not in by_name, f"duplicate release job name: {name}")
        ids.add(job_id)
        by_name[name] = job
        job_run_id = _exact_int(job.get("run_id"), field=f"release job {name} run_id")
        job_attempt = _exact_int(job.get("run_attempt"), field=f"release job {name} run_attempt")
        _require(job_run_id == expected_run_id, f"release job {name} has wrong run_id")
        _require(
            job_attempt == expected_attempt,
            f"release job {name} has wrong run_attempt",
        )
        _require(job.get("status") == "completed", f"release job {name} is not completed")
        conclusion = job.get("conclusion")
        _require(
            conclusion in {"success", "skipped"},
            f"release job {name} has unsafe conclusion: {conclusion!r}",
        )
        if conclusion == "skipped":
            skipped.add(name)
    _require(
        skipped == EXPECTED_SKIPPED_JOBS,
        f"release workflow has unexpected skipped jobs: {sorted(skipped)!r}",
    )

    successful_jobs = release_workflow.get("successful_jobs")
    _require(isinstance(successful_jobs, list), "evidence successful_jobs must be an array")
    assert isinstance(successful_jobs, list)
    for index, recorded in enumerate(successful_jobs):
        expected_job = _require_mapping(recorded, source=f"evidence successful job {index}")
        name = expected_job.get("name")
        job_id = expected_job.get("id")
        _require(isinstance(name, str), f"evidence successful job {index} has no name")
        actual = by_name.get(name)
        _require(actual is not None, f"required successful release job is missing: {name}")
        assert actual is not None
        _require(actual.get("id") == job_id, f"release job id differs from evidence: {name}")
        _require(
            actual.get("conclusion") == "success",
            f"required release job did not succeed: {name}",
        )


def verify_release_workflow(
    evidence: JsonMapping,
    *,
    token: str | None,
    request_json: RequestJson = _request_json,
) -> None:
    release_workflow = _require_mapping(
        evidence.get("release_workflow"), source="release_workflow evidence"
    )
    run_id = _exact_int(release_workflow.get("run_id"), field="evidence run_id")
    attempt = _exact_int(release_workflow.get("run_attempt"), field="evidence run_attempt")
    base = f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}/attempts/{attempt}"
    run_payload = request_json(base, token=token)
    jobs_payload = request_json(f"{base}/jobs?per_page=100", token=token)
    validate_release_workflow(run_payload, jobs_payload, release_workflow)


def _normalized_specifiers(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def validate_pypi_metadata(pypi_payload: object, evidence: JsonMapping) -> JsonMapping:
    pypi = _require_mapping(pypi_payload, source="PyPI release response")
    info = _require_mapping(pypi.get("info"), source="PyPI info")
    _require(info.get("name") == PACKAGE, "PyPI package name is not exact")
    _require(info.get("version") == VERSION, "PyPI version is not exact")
    requires_python = info.get("requires_python")
    _require(isinstance(requires_python, str), "PyPI requires_python is missing")
    assert isinstance(requires_python, str)
    _require(
        _normalized_specifiers(requires_python) == EXPECTED_REQUIRES_PYTHON,
        "PyPI requires_python differs from the exact 2.2 contract",
    )
    description = info.get("description")
    _require(isinstance(description, str), "PyPI description is missing")
    assert isinstance(description, str)
    _require(
        _sha256(description.encode("utf-8")) == evidence["pypi_description_sha256"],
        "PyPI description digest differs from Phase E evidence",
    )
    urls = pypi.get("urls")
    _require(isinstance(urls, list), "PyPI release response has no urls array")
    assert isinstance(urls, list)
    names: list[str] = []
    for index, value in enumerate(urls):
        item = _require_mapping(value, source=f"PyPI distribution {index}")
        name = item.get("filename")
        _require(isinstance(name, str), f"PyPI distribution {index} has no filename")
        assert isinstance(name, str)
        names.append(name)
    _require(
        set(names) == EXPECTED_DISTRIBUTION_NAMES,
        "PyPI does not expose the exact three 2.2.0 distributions",
    )
    _require(len(names) == len(set(names)), "PyPI has duplicate distribution names")
    return pypi


def _safe_download_url(url: object, *, source: str, hosts: frozenset[str]) -> str:
    _require(isinstance(url, str), f"{source} has no download URL")
    assert isinstance(url, str)
    parsed = urllib.parse.urlparse(url)
    _require(
        parsed.scheme == "https" and parsed.hostname in hosts,
        f"{source} has an unsafe download URL: {url!r}",
    )
    return url


def _download_github_assets(
    release: JsonMapping,
    dist_dir: Path,
    *,
    token: str | None,
    request_bytes: RequestBytes,
) -> dict[str, bytes]:
    assets = release.get("assets")
    _require(isinstance(assets, list), "GitHub Release has no assets array")
    assert isinstance(assets, list)
    expected_by_name = {str(item["name"]): item for item in EXPECTED_RELEASE_ASSETS}
    actual_by_name: dict[str, JsonMapping] = {}
    for index, value in enumerate(assets):
        item = _require_mapping(value, source=f"GitHub Release asset {index}")
        name = item.get("name")
        _require(isinstance(name, str), f"GitHub Release asset {index} has no name")
        assert isinstance(name, str)
        _require(name not in actual_by_name, f"GitHub Release has duplicate asset: {name}")
        actual_by_name[name] = item
    _require(
        set(actual_by_name) == set(expected_by_name),
        "GitHub Release does not expose the exact five Phase E assets",
    )
    downloaded: dict[str, bytes] = {}
    for name, expected in expected_by_name.items():
        item = actual_by_name[name]
        _require(
            item.get("digest") == f"sha256:{expected['sha256']}",
            f"GitHub Release digest differs for {name}",
        )
        _require(item.get("size") == expected["size"], f"GitHub Release size differs for {name}")
        url = _safe_download_url(
            item.get("browser_download_url"),
            source=f"GitHub Release asset {name}",
            hosts=frozenset({"github.com"}),
        )
        data = request_bytes(url, token=token)
        _require(len(data) == expected["size"], f"downloaded GitHub asset size differs: {name}")
        _require(
            _sha256(data) == expected["sha256"],
            f"downloaded GitHub asset digest differs: {name}",
        )
        (dist_dir / name).write_bytes(data)
        downloaded[name] = data
    return downloaded


def _verify_pypi_bytes(
    pypi: JsonMapping,
    github_bytes: Mapping[str, bytes],
    *,
    request_bytes: RequestBytes,
) -> None:
    urls = pypi["urls"]
    assert isinstance(urls, list)
    by_name = {str(item["filename"]): item for item in urls if isinstance(item, Mapping)}
    for name in sorted(EXPECTED_DISTRIBUTION_NAMES):
        item = _require_mapping(by_name[name], source=f"PyPI distribution {name}")
        url = _safe_download_url(
            item.get("url"),
            source=f"PyPI distribution {name}",
            hosts=frozenset({"files.pythonhosted.org"}),
        )
        data = request_bytes(url)
        _require(data == github_bytes[name], f"PyPI and GitHub bytes differ for {name}")


def verify_public_state(
    root: Path,
    evidence: JsonMapping,
    old_manifest_raw: bytes,
    *,
    token: str | None,
    request_json: RequestJson = _request_json,
    request_bytes: RequestBytes = _request_bytes,
) -> None:
    pypi_url = f"https://pypi.org/pypi/{PACKAGE}/{VERSION}/json"
    tag_url = f"https://api.github.com/repos/{REPOSITORY}/git/ref/tags/{TAG}"
    release_url = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{TAG}"
    pypi = validate_pypi_metadata(request_json(pypi_url), evidence)
    tag = _require_mapping(request_json(tag_url, token=token), source="GitHub tag response")
    release = _require_mapping(
        request_json(release_url, token=token), source="GitHub Release response"
    )
    body = release.get("body")
    _require(isinstance(body, str), "GitHub Release body is missing")
    assert isinstance(body, str)
    _require(
        _sha256(body.encode("utf-8")) == evidence["release_notes_sha256"],
        "GitHub Release notes digest differs from Phase E evidence",
    )

    with tempfile.TemporaryDirectory(prefix="swirengine-public-2.2-evidence-") as temp:
        temp_root = Path(temp)
        dist_dir = temp_root / "dist"
        dist_dir.mkdir()
        old_manifest = temp_root / "publication-required-workflows.json"
        old_manifest.write_bytes(old_manifest_raw)
        github_bytes = _download_github_assets(
            release,
            dist_dir,
            token=token,
            request_bytes=request_bytes,
        )
        evidence_errors = verify_evidence(
            dist_dir,
            candidate_source_commit=str(evidence["candidate_source_commit"]),
            candidate_marker_commit=str(evidence["candidate_marker_commit"]),
            publication_commit=str(evidence["publication_commit"]),
            workflow_manifest=old_manifest,
            expected_workflow_manifest_sha256=str(
                evidence["publication_required_workflows_sha256"]
            ),
            expected_logical_sdist_sha256=str(evidence["logical_sdist_sha256"]),
        )
        _require(not evidence_errors, f"published release evidence is invalid: {evidence_errors!r}")
        expected = load_expected_release(
            dist_dir,
            publication_commit=str(evidence["publication_commit"]),
            release_notes=root / RELEASE_NOTES,
        )
        expected_assets = [item.as_dict() for item in expected.release_assets]
        _require(
            expected_assets == evidence["release_assets"],
            "downloaded release assets differ from Phase E evidence",
        )
        plan = reconcile_release(
            expected,
            ReleaseSnapshot(pypi=pypi, tag=tag, release=release),
        )
        _require(plan.complete, f"public release state is incomplete: {plan.as_dict()!r}")
        _verify_pypi_bytes(pypi, github_bytes, request_bytes=request_bytes)


def verify_public_install() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-public-2.2-install-") as temp:
        temp_root = Path(temp)
        environment = temp_root / "venv"
        probe_root = temp_root / "probe"
        probe_root.mkdir()
        env = dict(os.environ)
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_TOKEN", None)
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        subprocess.run(
            [sys.executable, "-m", "venv", str(environment)],
            check=True,
            cwd=probe_root,
            env=env,
        )
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--index-url",
                "https://pypi.org/simple",
                f"{PACKAGE}=={VERSION}",
            ],
            check=True,
            cwd=probe_root,
            env=env,
        )
        probe = (
            "import swirengine; "
            f"assert swirengine.__version__ == {VERSION!r}; "
            "assert all(hasattr(swirengine, name) "
            "for name in ('Game', 'Scene', 'Color', 'Vec3')); "
            "print(swirengine.__version__, swirengine.__file__)"
        )
        subprocess.run([str(python), "-c", probe], check=True, cwd=probe_root, env=env)


def verify(
    root: Path,
    evidence_path: Path,
    *,
    skip_install: bool,
) -> None:
    root = root.resolve()
    if not evidence_path.is_absolute():
        evidence_path = root / evidence_path
    evidence = load_evidence(evidence_path)
    old_manifest_raw = verify_repository_evidence(root, evidence)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    verify_release_workflow(evidence, token=token)
    verify_public_state(root, evidence, old_manifest_raw, token=token)
    if not skip_install:
        verify_public_install()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the immutable public SwirEngine 2.2.0 release and Phase E evidence."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--skip-install", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        verify(args.root, args.evidence, skip_install=args.skip_install)
    except (
        OSError,
        subprocess.CalledProcessError,
        PublicationChainError,
        ReleaseEvidenceError,
        ReleaseReconciliationError,
        PublicReleaseVerificationError,
    ) as exc:
        print(f"SwirEngine {VERSION} public release verification FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        f"SwirEngine {VERSION} public release verified: "
        f"{PUBLICATION_COMMIT}, run {RELEASE_RUN_ID} attempt {RELEASE_RUN_ATTEMPT}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
