from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from tools._release_adapter_2_2_1 import load_isolated_release_module
    from tools.reconcile_release_2_2_1 import (
        ReleaseReconciliationError,
        ReleaseSnapshot,
        load_expected_release,
        reconcile_release,
    )
    from tools.release_evidence_2_2_1 import ReleaseEvidenceError, verify_evidence
    from tools.verify_publication_chain_2_2_1 import (
        PublicationChainError,
        verify_chain,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from _release_adapter_2_2_1 import load_isolated_release_module
    from reconcile_release_2_2_1 import (
        ReleaseReconciliationError,
        ReleaseSnapshot,
        load_expected_release,
        reconcile_release,
    )
    from release_evidence_2_2_1 import ReleaseEvidenceError, verify_evidence
    from verify_publication_chain_2_2_1 import (
        PublicationChainError,
        verify_chain,
    )

SCHEMA = "swirengine-public-release-evidence-v4"
REPOSITORY = "Swir/SwirEngine"
PACKAGE = "swirengine"
VERSION = "2.2.1"
TAG = "v2.2.1"
EXPECTED_REQUIRES_PYTHON = frozenset({">=3.10", "<3.15"})
DEFAULT_EVIDENCE = Path("release-evidence/2.2.1/manifest.json")
WORKFLOW_MANIFEST = PurePosixPath(".github/release-gates/2.2.1-required-workflows.json")
RELEASE_NOTES = Path("RELEASE_NOTES_2_2_1.md")
PYPI_DESCRIPTION = Path("PYPI_DESCRIPTION_2_2_1.md")
POST_RELEASE_WORKFLOW = Path(".github/workflows/post-release-2.2.1.yml")
RETIRED_CANDIDATE_WORKFLOW = Path(".github/workflows/release-candidate-2.2.1.yml")
CANDIDATE_WORKFLOW_FIXTURE = Path("tests/fixtures/release-candidate-2.2.1.yml")
HISTORICAL_CANDIDATE_HEADER = (
    b"# Historical SwirEngine 2.2.1 Phase B workflow fixture. "
    b"It is intentionally inactive.\n"
)

CANDIDATE_SOURCE_COMMIT = "c2fa0ba9ba4b0a4eb3f1bde0da2e5f8a681e2b7e"
CANDIDATE_WORKFLOW_SHA256 = (
    "b8892c8c1aea299099f7ae8e81901678add4f7914fc578aae7bac2b141a6cda4"
)
CANDIDATE_MARKER_COMMIT = "47c15f8a4c80318a31762133e0cf4d8524b82564"
PUBLICATION_COMMIT = "8d27fdb3c37fd79b93a2f3ab420b763de564c9e9"
PUBLICATION_REQUIRED_WORKFLOWS_SHA256 = (
    "d75b8dbd9afed9b6fe4df7892dbebcd009ea57bd87e0c1de8046085bc7b56d0a"
)
PHASE_E_REQUIRED_WORKFLOWS_SHA256 = (
    "a04ea73f89974ee4e0d58d132cad0c849a492bc6615788174a305b407bef2eb0"
)
LOGICAL_SDIST_SHA256 = "0329fbfcfdd42364091a72e8d0808f2d584793a13ac5fd366f11a8e03ffdd27d"
RELEASE_NOTES_SHA256 = "1fc0fae524089ca45c0b8a80bde08c3befb150c77290bc372bbfc4d0985719fd"
PYPI_DESCRIPTION_SHA256 = "e8822f1cc9941d2e09a105d686003f2ffe70e7352bd35196c17b24f24767556b"
RELEASE_RUN_ID = 37183110375
RELEASE_RUN_ATTEMPT = 2
TRUSTED_WORKFLOW_COMMIT = "3577e2fc25e3bf1604630a844851b5052abc7639"

EXPECTED_RELEASE_ASSETS = (
    {
        "name": "SHA256SUMS",
        "sha256": "1cbc2f69adae97fd7b74ff828ba24768beeaf5f5f5e634421a72962e1a4e7e7d",
        "size": 299,
    },
    {
        "name": "release-provenance.json",
        "sha256": "d67ff60c0694f1229a1261bb9a267c28dfd911a31e96d77262f3ff44b1b4ce8c",
        "size": 1064,
    },
    {
        "name": "swirengine-2.2.1-cp314-cp314-win_amd64.whl",
        "sha256": "4ee9257831aab322f9da220feebe01fc25ecb8e5191f0a3ead0a2933a0304f1b",
        "size": 948619,
    },
    {
        "name": "swirengine-2.2.1-py3-none-any.whl",
        "sha256": "e61be3dbe011ff6035b65111e99478127b918f57f900c6803e3d649a44a41379",
        "size": 830462,
    },
    {
        "name": "swirengine-2.2.1.tar.gz",
        "sha256": "e1505898990d98d33a8f83075933220b87a3e2fe1269f77bfdd350f02a27915c",
        "size": 2925167,
    },
)
EXPECTED_DISTRIBUTION_NAMES = frozenset(
    item["name"]
    for item in EXPECTED_RELEASE_ASSETS
    if str(item["name"]).endswith((".whl", ".tar.gz"))
)
EXPECTED_SUCCESSFUL_JOBS = (
    {"id": 111381335366, "name": "Fresh-read and verify exact PyPI files"},
    {"id": 111381242818, "name": "Fresh-read and verify immutable GitHub Release"},
    {
        "id": 111381018856,
        "name": "Generate provenance and take initial public-state snapshot",
    },
    {
        "id": 111381365706,
        "name": "Public PyPI verify / macos-latest / Python 3.13",
    },
    {
        "id": 111381365661,
        "name": "Public PyPI verify / ubuntu-latest / Python 3.13",
    },
    {
        "id": 111381365690,
        "name": "Public PyPI verify / windows-latest / Python 3.14",
    },
    {"id": 111380820056, "name": "Verify immutable publication chain and trigger"},
    {
        "id": 111381456957,
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
    "path": ".github/workflows/release-candidate-2.2.1.yml",
    "name": "SwirEngine 2.2.1 Release Candidate",
}
NEW_WORKFLOW_ENTRY = {
    "path": ".github/workflows/post-release-2.2.1.yml",
    "name": "Post-release 2.2.1 Public Verification",
}

JsonMapping = Mapping[str, Any]

_BASE: Any = load_isolated_release_module(
    "verify_public_release_2_2.py",
    "tools._verify_public_release_2_2_1_base",
)

# Reuse the exercised 2.2.0 verifier implementation under an isolated module
# identity. Only immutable 2.2.1 constants and version-specific helpers are
# replaced; the imported 2.2.0 verifier remains untouched.
for _name, _value in {
    "SCHEMA": SCHEMA,
    "REPOSITORY": REPOSITORY,
    "PACKAGE": PACKAGE,
    "VERSION": VERSION,
    "TAG": TAG,
    "EXPECTED_REQUIRES_PYTHON": EXPECTED_REQUIRES_PYTHON,
    "DEFAULT_EVIDENCE": DEFAULT_EVIDENCE,
    "WORKFLOW_MANIFEST": WORKFLOW_MANIFEST,
    "RELEASE_NOTES": RELEASE_NOTES,
    "PYPI_DESCRIPTION": PYPI_DESCRIPTION,
    "POST_RELEASE_WORKFLOW": POST_RELEASE_WORKFLOW,
    "RETIRED_CANDIDATE_WORKFLOW": RETIRED_CANDIDATE_WORKFLOW,
    "CANDIDATE_SOURCE_COMMIT": CANDIDATE_SOURCE_COMMIT,
    "CANDIDATE_MARKER_COMMIT": CANDIDATE_MARKER_COMMIT,
    "PUBLICATION_COMMIT": PUBLICATION_COMMIT,
    "PUBLICATION_REQUIRED_WORKFLOWS_SHA256": PUBLICATION_REQUIRED_WORKFLOWS_SHA256,
    "PHASE_E_REQUIRED_WORKFLOWS_SHA256": PHASE_E_REQUIRED_WORKFLOWS_SHA256,
    "LOGICAL_SDIST_SHA256": LOGICAL_SDIST_SHA256,
    "RELEASE_NOTES_SHA256": RELEASE_NOTES_SHA256,
    "PYPI_DESCRIPTION_SHA256": PYPI_DESCRIPTION_SHA256,
    "RELEASE_RUN_ID": RELEASE_RUN_ID,
    "RELEASE_RUN_ATTEMPT": RELEASE_RUN_ATTEMPT,
    "TRUSTED_WORKFLOW_COMMIT": TRUSTED_WORKFLOW_COMMIT,
    "EXPECTED_RELEASE_ASSETS": EXPECTED_RELEASE_ASSETS,
    "EXPECTED_DISTRIBUTION_NAMES": EXPECTED_DISTRIBUTION_NAMES,
    "EXPECTED_SUCCESSFUL_JOBS": EXPECTED_SUCCESSFUL_JOBS,
    "EXPECTED_SKIPPED_JOBS": EXPECTED_SKIPPED_JOBS,
    "OLD_WORKFLOW_ENTRY": OLD_WORKFLOW_ENTRY,
    "NEW_WORKFLOW_ENTRY": NEW_WORKFLOW_ENTRY,
    "verify_chain": verify_chain,
    "verify_evidence": verify_evidence,
    "load_expected_release": load_expected_release,
    "reconcile_release": reconcile_release,
    "ReleaseSnapshot": ReleaseSnapshot,
}.items():
    setattr(_BASE, _name, _value)

PublicReleaseVerificationError = _BASE.PublicReleaseVerificationError
_canonical_json = _BASE._canonical_json
_sha256 = _BASE._sha256
_require = _BASE._require
_verify_pypi_bytes = _BASE._verify_pypi_bytes
expected_evidence = _BASE.expected_evidence
load_evidence = _BASE.load_evidence
validate_release_workflow = _BASE.validate_release_workflow
verify_release_workflow = _BASE.verify_release_workflow


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
    _require(len(normalized) == 48, f"{source} workflow manifest must contain 48 entries")
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
        old_payload = _BASE.json.loads(
            old_raw.decode("utf-8"), parse_constant=_BASE._reject_json_constant
        )
        new_payload = _BASE.json.loads(
            new_raw.decode("utf-8"), parse_constant=_BASE._reject_json_constant
        )
    except (UnicodeDecodeError, _BASE.json.JSONDecodeError) as exc:
        raise PublicReleaseVerificationError(
            f"invalid required-workflow manifest JSON: {exc}"
        ) from exc
    old = _workflow_manifest(old_payload, source="publication")
    new = _workflow_manifest(new_payload, source="Phase E")
    _require(len(old) == len(new), "Phase E workflow manifest changed entry count")
    changed = [
        index
        for index, pair in enumerate(zip(old, new, strict=True))
        if pair[0] != pair[1]
    ]
    _require(changed == [47], "Phase E must replace exactly one same-position workflow entry")
    index = changed[0]
    _require(old[index] == OLD_WORKFLOW_ENTRY, "Phase E did not retire the exact 2.2.1 candidate gate")
    _require(new[index] == NEW_WORKFLOW_ENTRY, "Phase E did not add the exact 2.2.1 public verifier gate")


_BASE._workflow_manifest = _workflow_manifest
_BASE.validate_required_workflow_transition = validate_required_workflow_transition
_BASE_VALIDATE_PYPI_METADATA = _BASE.validate_pypi_metadata


def _require_regular_file(path: Path, *, subject: str) -> None:
    _require(
        path.is_file() and not path.is_symlink(),
        f"{subject} is missing or unsafe",
    )


def _validate_candidate_workflow_fixture(
    fixture: Path,
    candidate_workflow: bytes,
) -> None:
    _require(
        _sha256(candidate_workflow) == CANDIDATE_WORKFLOW_SHA256,
        "historical 2.2.1 candidate workflow differs from the immutable C workflow digest",
    )
    try:
        actual = fixture.read_bytes()
    except OSError as exc:
        raise PublicReleaseVerificationError(
            f"cannot read historical 2.2.1 candidate workflow fixture: {exc}"
        ) from exc
    _require(
        actual.startswith(HISTORICAL_CANDIDATE_HEADER),
        "historical 2.2.1 candidate workflow fixture lacks the exact header",
    )
    fixture_workflow = actual[len(HISTORICAL_CANDIDATE_HEADER) :]
    _require(
        _sha256(fixture_workflow) == CANDIDATE_WORKFLOW_SHA256,
        "historical 2.2.1 candidate workflow fixture body digest is not immutable",
    )
    _require(
        fixture_workflow == candidate_workflow,
        "historical 2.2.1 candidate workflow fixture is not the exact header plus C workflow",
    )


def verify_repository_evidence(root: Path, evidence: JsonMapping) -> bytes:
    resolved = root.resolve()
    for relative, subject in (
        (POST_RELEASE_WORKFLOW, "Phase E public workflow"),
        (RELEASE_NOTES, "release notes"),
        (PYPI_DESCRIPTION, "PyPI description"),
        (CANDIDATE_WORKFLOW_FIXTURE, "historical 2.2.1 candidate workflow fixture"),
    ):
        _require_regular_file(resolved / relative, subject=subject)
    fixture = resolved / CANDIDATE_WORKFLOW_FIXTURE
    candidate_workflow = _BASE._git_bytes(
        resolved,
        "show",
        f"{CANDIDATE_SOURCE_COMMIT}:{RETIRED_CANDIDATE_WORKFLOW.as_posix()}",
    )
    _validate_candidate_workflow_fixture(fixture, candidate_workflow)
    old_raw = _BASE.verify_repository_evidence(resolved, evidence)
    return old_raw


def validate_pypi_metadata(pypi_payload: object, evidence: JsonMapping) -> JsonMapping:
    pypi = _BASE_VALIDATE_PYPI_METADATA(pypi_payload, evidence)
    info = pypi.get("info")
    _require(isinstance(info, Mapping), "PyPI info is missing")
    assert isinstance(info, Mapping)
    _require(
        info.get("description_content_type") == "text/markdown",
        "PyPI description_content_type must be exactly text/markdown",
    )
    urls = pypi.get("urls")
    assert isinstance(urls, list)
    for index, value in enumerate(urls):
        _require(isinstance(value, Mapping), f"PyPI distribution {index} must be an object")
        assert isinstance(value, Mapping)
        _require(
            value.get("yanked") is False,
            f"PyPI distribution {index} is yanked or lacks explicit yanked=false",
        )
    return pypi


_BASE.validate_pypi_metadata = validate_pypi_metadata


def verify_public_install() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-public-2.2.1-install-") as temp:
        temp_root = Path(temp)
        environment = temp_root / "venv"
        probe_root = temp_root / "probe"
        probe_root.mkdir()
        env = dict(os.environ)
        blocked = {
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "PYTHONHOME",
            "PYTHONPATH",
        }
        for name in tuple(env):
            normalized = name.upper()
            if normalized in blocked or normalized.startswith("PIP_"):
                env.pop(name)
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
                "--isolated",
                "install",
                "--disable-pip-version-check",
                "--no-input",
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


def verify_public_state(
    root: Path,
    evidence: JsonMapping,
    old_manifest_raw: bytes,
    *,
    token: str | None,
    request_json: Any = _BASE._request_json,
    request_bytes: Any = _BASE._request_bytes,
) -> None:
    _BASE.verify_public_state(
        root,
        evidence,
        old_manifest_raw,
        token=token,
        request_json=request_json,
        request_bytes=request_bytes,
    )


def verify(root: Path, evidence_path: Path, *, skip_install: bool) -> None:
    root = root.resolve()
    if not evidence_path.is_absolute():
        evidence_path = root / evidence_path
    evidence = load_evidence(evidence_path)
    old_manifest_raw = verify_repository_evidence(root, evidence)
    token = _BASE.os.environ.get("GH_TOKEN") or _BASE.os.environ.get("GITHUB_TOKEN")
    verify_release_workflow(evidence, token=token)
    verify_public_state(root, evidence, old_manifest_raw, token=token)
    if not skip_install:
        verify_public_install()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the immutable public SwirEngine 2.2.1 release and Phase E evidence."
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
        _BASE.subprocess.CalledProcessError,
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
