from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from tools.verify_public_release_2_2 import (
    DEFAULT_EVIDENCE,
    EXPECTED_DISTRIBUTION_NAMES,
    EXPECTED_RELEASE_ASSETS,
    EXPECTED_SKIPPED_JOBS,
    EXPECTED_SUCCESSFUL_JOBS,
    PUBLICATION_COMMIT,
    PYPI_DESCRIPTION,
    RELEASE_RUN_ATTEMPT,
    RELEASE_RUN_ID,
    REPOSITORY,
    TRUSTED_WORKFLOW_COMMIT,
    PublicReleaseVerificationError,
    _parser,
    _verify_pypi_bytes,
    expected_evidence,
    load_evidence,
    validate_pypi_metadata,
    validate_release_workflow,
    validate_required_workflow_transition,
    verify_public_install,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / DEFAULT_EVIDENCE
WORKFLOW_MANIFEST = ".github/release-gates/2.2-required-workflows.json"
BYTE_BOUND_FILES = {
    "/release-evidence/2.2.0/manifest.json text eol=lf",
    "/.github/release-gates/2.2-required-workflows.json text eol=lf",
    "/RELEASE_NOTES_2_2.md text eol=lf",
    "/PYPI_DESCRIPTION_2_2.md text eol=lf",
}
PATCH_BYTE_BOUND_FILES = {
    "/.github/release-gates/2.2.1-required-workflows.json text eol=lf",
    "/RELEASE_NOTES_2_2_1.md text eol=lf",
    "/PYPI_DESCRIPTION_2_2_1.md text eol=lf",
    "/tools/verify_public_release_2_2.py text eol=lf",
    "/tools/verify_publication_chain_2_2.py text eol=lf",
    "/tools/candidate_evidence_2_2.py text eol=lf",
    "/tools/release_evidence_2_2.py text eol=lf",
    "/tools/reconcile_release_2_2.py text eol=lf",
    "/.github/workflows/post-release-2.2.yml text eol=lf",
    "/.github/workflows/publication-gate-2.2.yml text eol=lf",
}


def _run(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": RELEASE_RUN_ID,
        "name": "Release",
        "path": ".github/workflows/release.yml",
        "event": "workflow_run",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": RELEASE_RUN_ATTEMPT,
        "head_branch": "main",
        "head_sha": TRUSTED_WORKFLOW_COMMIT,
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
    }
    payload.update(overrides)
    return payload


def _job(job_id: int, name: str, conclusion: str = "success") -> dict[str, object]:
    return {
        "id": job_id,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "run_id": RELEASE_RUN_ID,
        "run_attempt": RELEASE_RUN_ATTEMPT,
    }


def _jobs() -> dict[str, object]:
    jobs = [_job(int(item["id"]), str(item["name"])) for item in EXPECTED_SUCCESSFUL_JOBS]
    jobs.extend(
        _job(RELEASE_RUN_ID + index, name, "skipped")
        for index, name in enumerate(sorted(EXPECTED_SKIPPED_JOBS), start=1)
    )
    jobs.append(_job(RELEASE_RUN_ID + 100, "Build and compare exact candidate/publication source"))
    return {"total_count": len(jobs), "jobs": jobs}


def _old_manifest() -> bytes:
    payload = json.loads((ROOT / WORKFLOW_MANIFEST).read_bytes())
    workflows = payload["required_workflows"]
    assert workflows[19] == {
        "path": ".github/workflows/post-release-2.2.yml",
        "name": "Post-release 2.2 Public Verification",
    }
    workflows[19] = {
        "path": ".github/workflows/release-candidate-2.2.yml",
        "name": "SwirEngine 2.2 Release Candidate",
    }
    return (json.dumps(payload, indent=2) + "\n").encode()


def _new_manifest(old_raw: bytes) -> bytes:
    payload = json.loads(old_raw)
    workflows = payload["required_workflows"]
    assert workflows[19] == {
        "path": ".github/workflows/release-candidate-2.2.yml",
        "name": "SwirEngine 2.2 Release Candidate",
    }
    workflows[19] = {
        "path": ".github/workflows/post-release-2.2.yml",
        "name": "Post-release 2.2 Public Verification",
    }
    return (json.dumps(payload, indent=2) + "\n").encode()


def _pypi(description: str | None = None) -> dict[str, object]:
    if description is None:
        description = (ROOT / PYPI_DESCRIPTION).read_text(encoding="utf-8")
    return {
        "info": {
            "name": "swirengine",
            "version": "2.2.0",
            "requires_python": ">=3.10, <3.15",
            "description": description,
        },
        "urls": [
            {
                "filename": name,
                "url": f"https://files.pythonhosted.org/packages/{name}",
            }
            for name in sorted(EXPECTED_DISTRIBUTION_NAMES)
        ],
    }


def test_manifest_is_the_single_canonical_v4_record() -> None:
    evidence = load_evidence(EVIDENCE)

    assert evidence == expected_evidence()
    assert evidence["schema"] == "swirengine-public-release-evidence-v4"
    assert evidence["publication_commit"] == PUBLICATION_COMMIT
    assert evidence["release_assets"] == list(EXPECTED_RELEASE_ASSETS)
    assert evidence["release_workflow"]["successful_jobs"] == list(EXPECTED_SUCCESSFUL_JOBS)
    assert [item["name"] for item in evidence["release_assets"]] == sorted(
        item["name"] for item in evidence["release_assets"]
    )
    assert [item["name"] for item in evidence["release_workflow"]["successful_jobs"]] == sorted(
        item["name"] for item in evidence["release_workflow"]["successful_jobs"]
    )


def test_byte_bound_release_evidence_forces_lf_on_every_platform() -> None:
    attributes = {
        line
        for line in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }

    assert BYTE_BOUND_FILES <= attributes
    assert PATCH_BYTE_BOUND_FILES <= attributes


def test_manifest_rejects_noncanonical_rendering(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(json.dumps(expected_evidence()).encode())

    with pytest.raises(PublicReleaseVerificationError, match="not canonical"):
        load_evidence(path)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("publication_commit",), "0" * 40),
        (("pypi_description_sha256",), "f" * 64),
        (("release_workflow", "run_id"), 37174331751),
        (("release_assets", 0, "size"), 300),
    ],
)
def test_manifest_rejects_any_canonical_data_drift(
    tmp_path: Path,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    payload: object = deepcopy(expected_evidence())
    target = payload
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    evidence_path = tmp_path / "manifest.json"
    evidence_path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())

    with pytest.raises(PublicReleaseVerificationError, match="exact accepted"):
        load_evidence(evidence_path)


def test_exact_attempt_scoped_authority_jobs_are_accepted() -> None:
    evidence = expected_evidence()

    validate_release_workflow(_run(), _jobs(), evidence["release_workflow"])


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": 37174331751}, "unexpected id"),
        ({"run_attempt": 2}, "unexpected run_attempt"),
        ({"head_sha": "0" * 40}, "unexpected head_sha"),
        ({"conclusion": "failure"}, "unexpected conclusion"),
        ({"head_repository": {"full_name": "example/fork"}}, "head_repository"),
    ],
)
def test_release_run_identity_is_exact(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(PublicReleaseVerificationError, match=message):
        validate_release_workflow(
            _run(**overrides),
            _jobs(),
            expected_evidence()["release_workflow"],
        )


def test_rejects_old_success_run_with_unexpanded_skipped_public_matrix() -> None:
    jobs = _jobs()
    values = jobs["jobs"]
    assert isinstance(values, list)
    values[:] = [
        item for item in values if not str(item["name"]).startswith("Public PyPI verify /")
    ]
    values.append(
        _job(
            111354122709,
            "Public PyPI verify / ${{ matrix.os }} / Python ${{ matrix.python-version }}",
            "skipped",
        )
    )
    jobs["total_count"] = len(values)

    with pytest.raises(PublicReleaseVerificationError, match="unexpanded matrix placeholder"):
        validate_release_workflow(
            _run(),
            jobs,
            expected_evidence()["release_workflow"],
        )


def test_rejects_skipped_authority_job_even_when_run_is_success() -> None:
    jobs = _jobs()
    values = jobs["jobs"]
    assert isinstance(values, list)
    target = next(
        item for item in values if item["name"] == "Fresh-read and verify exact PyPI files"
    )
    target["conclusion"] = "skipped"

    with pytest.raises(PublicReleaseVerificationError, match="unexpected skipped jobs"):
        validate_release_workflow(
            _run(),
            jobs,
            expected_evidence()["release_workflow"],
        )


def test_rejects_duplicate_or_incomplete_attempt_scoped_jobs() -> None:
    duplicate = _jobs()
    duplicate_values = duplicate["jobs"]
    assert isinstance(duplicate_values, list)
    duplicate_values.append(dict(duplicate_values[0]))
    duplicate["total_count"] = len(duplicate_values)
    with pytest.raises(PublicReleaseVerificationError, match="duplicate release job"):
        validate_release_workflow(
            _run(),
            duplicate,
            expected_evidence()["release_workflow"],
        )

    incomplete = _jobs()
    incomplete["total_count"] = int(incomplete["total_count"]) + 1
    with pytest.raises(PublicReleaseVerificationError, match="incomplete"):
        validate_release_workflow(
            _run(),
            incomplete,
            expected_evidence()["release_workflow"],
        )


def test_phase_e_manifest_is_an_exact_same_position_transition() -> None:
    old_raw = _old_manifest()

    validate_required_workflow_transition(old_raw, _new_manifest(old_raw))


def test_phase_e_manifest_rejects_any_second_change() -> None:
    old_raw = _old_manifest()
    payload = json.loads(_new_manifest(old_raw))
    payload["required_workflows"][0]["name"] = "Changed too"
    changed = (json.dumps(payload, indent=2) + "\n").encode()

    with pytest.raises(PublicReleaseVerificationError, match="exactly one"):
        validate_required_workflow_transition(old_raw, changed)


def test_pypi_metadata_binds_description_python_range_and_exact_files() -> None:
    payload = _pypi()

    assert validate_pypi_metadata(payload, expected_evidence()) == payload

    payload["info"]["description"] += "tampered"  # type: ignore[index]
    with pytest.raises(PublicReleaseVerificationError, match="description digest"):
        validate_pypi_metadata(payload, expected_evidence())


def test_pypi_and_github_distribution_bytes_must_be_identical() -> None:
    pypi = _pypi()
    github_bytes = {name: name.encode() for name in EXPECTED_DISTRIBUTION_NAMES}

    def exact_download(url: str, **_: object) -> bytes:
        return github_bytes[url.rsplit("/", 1)[-1]]

    _verify_pypi_bytes(pypi, github_bytes, request_bytes=exact_download)

    def changed_download(url: str, **_: object) -> bytes:
        return exact_download(url) + b"tampered"

    with pytest.raises(PublicReleaseVerificationError, match="bytes differ"):
        _verify_pypi_bytes(pypi, github_bytes, request_bytes=changed_download)


def test_public_install_does_not_expose_repository_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def record_run(*_: object, **kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setenv("GH_TOKEN", "secret-gh")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-actions")
    monkeypatch.setattr(subprocess, "run", record_run)

    verify_public_install()

    assert len(calls) == 3
    for call in calls:
        env = call["env"]
        assert isinstance(env, dict)
        assert "GH_TOKEN" not in env
        assert "GITHUB_TOKEN" not in env
        assert "PYTHONPATH" not in env
        assert env["PYTHONNOUSERSITE"] == "1"


def test_cli_exposes_only_the_three_phase_e_controls() -> None:
    options = {
        option
        for action in _parser()._actions
        for option in action.option_strings
        if option != "--help" and option != "-h"
    }

    assert options == {"--root", "--evidence", "--skip-install"}
