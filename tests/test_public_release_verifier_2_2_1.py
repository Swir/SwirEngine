from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from tools import verify_public_release_2_2 as historical_verifier
from tools import verify_public_release_2_2_1 as verifier

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / verifier.DEFAULT_EVIDENCE
WORKFLOW_MANIFEST = ROOT / verifier.WORKFLOW_MANIFEST
BYTE_BOUND_FILES = {
    "/release-evidence/2.2.1/manifest.json text eol=lf",
    "/.github/release-gates/2.2.1-required-workflows.json text eol=lf",
    "/RELEASE_NOTES_2_2_1.md text eol=lf",
    "/PYPI_DESCRIPTION_2_2_1.md text eol=lf",
    "/tools/verify_public_release_2_2_1.py text eol=lf",
    "/.github/workflows/post-release-2.2.1.yml text eol=lf",
    "/tests/fixtures/release-candidate-2.2.1.yml text eol=lf",
}


def _run(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": verifier.RELEASE_RUN_ID,
        "name": "Release",
        "path": ".github/workflows/release.yml",
        "event": "workflow_run",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": verifier.RELEASE_RUN_ATTEMPT,
        "head_branch": "main",
        "head_sha": verifier.TRUSTED_WORKFLOW_COMMIT,
        "repository": {"full_name": verifier.REPOSITORY},
        "head_repository": {"full_name": verifier.REPOSITORY},
    }
    payload.update(overrides)
    return payload


def _job(job_id: int, name: str, conclusion: str = "success") -> dict[str, object]:
    return {
        "id": job_id,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "run_id": verifier.RELEASE_RUN_ID,
        "run_attempt": verifier.RELEASE_RUN_ATTEMPT,
    }


def _jobs() -> dict[str, object]:
    jobs = [
        _job(int(item["id"]), str(item["name"]))
        for item in verifier.EXPECTED_SUCCESSFUL_JOBS
    ]
    jobs.extend(
        _job(verifier.RELEASE_RUN_ID + index, name, "skipped")
        for index, name in enumerate(sorted(verifier.EXPECTED_SKIPPED_JOBS), start=1)
    )
    jobs.append(
        _job(
            verifier.RELEASE_RUN_ID + 100,
            "Build and compare exact candidate/publication source",
        )
    )
    return {"total_count": len(jobs), "jobs": jobs}


def _new_manifest() -> bytes:
    return WORKFLOW_MANIFEST.read_bytes()


def _old_manifest() -> bytes:
    payload = json.loads(_new_manifest())
    workflows = payload["required_workflows"]
    assert len(workflows) == 48
    assert workflows[47] == verifier.NEW_WORKFLOW_ENTRY
    workflows[47] = verifier.OLD_WORKFLOW_ENTRY
    return (json.dumps(payload, indent=2) + "\n").encode()


def _pypi(description: str | None = None) -> dict[str, object]:
    if description is None:
        description = (ROOT / verifier.PYPI_DESCRIPTION).read_text(encoding="utf-8")
    return {
        "info": {
            "name": "swirengine",
            "version": "2.2.1",
            "requires_python": ">=3.10, <3.15",
            "description": description,
            "description_content_type": "text/markdown",
        },
        "urls": [
            {
                "filename": name,
                "url": f"https://files.pythonhosted.org/packages/{name}",
                "yanked": False,
            }
            for name in sorted(verifier.EXPECTED_DISTRIBUTION_NAMES)
        ],
    }


def _candidate_workflow_bytes() -> bytes:
    return subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "show",
            (
                f"{verifier.CANDIDATE_SOURCE_COMMIT}:"
                f"{verifier.RETIRED_CANDIDATE_WORKFLOW.as_posix()}"
            ),
        ],
        check=True,
        capture_output=True,
    ).stdout


def test_manifest_is_the_single_canonical_v4_record() -> None:
    evidence = verifier.load_evidence(EVIDENCE)

    assert evidence == verifier.expected_evidence()
    assert evidence["schema"] == "swirengine-public-release-evidence-v4"
    assert evidence["version"] == "2.2.1"
    assert evidence["publication_commit"] == verifier.PUBLICATION_COMMIT
    assert evidence["release_assets"] == list(verifier.EXPECTED_RELEASE_ASSETS)
    assert evidence["release_workflow"]["successful_jobs"] == list(
        verifier.EXPECTED_SUCCESSFUL_JOBS
    )
    assert [item["name"] for item in evidence["release_assets"]] == sorted(
        item["name"] for item in evidence["release_assets"]
    )
    assert [item["name"] for item in evidence["release_workflow"]["successful_jobs"]] == sorted(
        item["name"] for item in evidence["release_workflow"]["successful_jobs"]
    )


def test_patch_verifier_does_not_mutate_historical_2_2_0_module() -> None:
    assert historical_verifier.VERSION == "2.2.0"
    assert historical_verifier.PUBLICATION_COMMIT == (
        "2f150ba6f3fd1e1fd121a8884298e616186e267b"
    )
    assert historical_verifier.RELEASE_RUN_ATTEMPT == 1


def test_byte_bound_release_evidence_forces_lf_on_every_platform() -> None:
    attributes = {
        line
        for line in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }

    assert BYTE_BOUND_FILES <= attributes


def test_manifest_rejects_noncanonical_rendering(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(json.dumps(verifier.expected_evidence()).encode())

    with pytest.raises(verifier.PublicReleaseVerificationError, match="not canonical"):
        verifier.load_evidence(path)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("publication_commit",), "0" * 40),
        (("phase_e_required_workflows_sha256",), "f" * 64),
        (("pypi_description_sha256",), "f" * 64),
        (("release_workflow", "run_attempt"), 1),
        (("release_assets", 0, "size"), 300),
    ],
)
def test_manifest_rejects_any_canonical_data_drift(
    tmp_path: Path,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    payload = deepcopy(verifier.expected_evidence())
    cursor: object = payload
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]
    evidence = tmp_path / "manifest.json"
    evidence.write_bytes(verifier._canonical_json(payload))

    with pytest.raises(verifier.PublicReleaseVerificationError, match="exact accepted"):
        verifier.load_evidence(evidence)


def test_repository_evidence_binds_chain_manifest_and_retired_candidate() -> None:
    old_raw = verifier.verify_repository_evidence(ROOT, verifier.expected_evidence())

    assert verifier._sha256(old_raw) == verifier.PUBLICATION_REQUIRED_WORKFLOWS_SHA256
    assert not (ROOT / verifier.RETIRED_CANDIDATE_WORKFLOW).exists()
    assert (ROOT / verifier.CANDIDATE_WORKFLOW_FIXTURE).read_bytes() == (
        verifier.HISTORICAL_CANDIDATE_HEADER + _candidate_workflow_bytes()
    )
    for relative in (
        verifier.POST_RELEASE_WORKFLOW,
        verifier.RELEASE_NOTES,
        verifier.PYPI_DESCRIPTION,
        verifier.CANDIDATE_WORKFLOW_FIXTURE,
    ):
        path = ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()


@pytest.mark.parametrize(
    "fixture_bytes",
    [
        pytest.param(
            lambda candidate: verifier.HISTORICAL_CANDIDATE_HEADER
            + candidate
            + b"# tampered\n",
            id="tampered-body",
        ),
        pytest.param(
            lambda candidate: b"# wrong historical header\n" + candidate,
            id="wrong-header",
        ),
        pytest.param(
            lambda candidate: (
                verifier.HISTORICAL_CANDIDATE_HEADER + candidate
            ).replace(b"\n", b"\r\n"),
            id="crlf-rewrite",
        ),
    ],
)
def test_candidate_fixture_rejects_any_byte_drift(
    tmp_path: Path,
    fixture_bytes: object,
) -> None:
    candidate = _candidate_workflow_bytes()
    fixture = tmp_path / "release-candidate-2.2.1.yml"
    assert callable(fixture_bytes)
    fixture.write_bytes(fixture_bytes(candidate))

    with pytest.raises(verifier.PublicReleaseVerificationError, match="exact header plus C"):
        verifier._validate_candidate_workflow_fixture(fixture, candidate)


@pytest.mark.parametrize(
    "unsafe_relative",
    [
        verifier.POST_RELEASE_WORKFLOW,
        verifier.RELEASE_NOTES,
        verifier.PYPI_DESCRIPTION,
        verifier.CANDIDATE_WORKFLOW_FIXTURE,
    ],
)
def test_repository_evidence_rejects_symlinked_contract_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_relative: Path,
) -> None:
    candidate = b"name: SwirEngine 2.2.1 Release Candidate\n"
    for relative in (
        verifier.POST_RELEASE_WORKFLOW,
        verifier.RELEASE_NOTES,
        verifier.PYPI_DESCRIPTION,
        verifier.CANDIDATE_WORKFLOW_FIXTURE,
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            verifier.HISTORICAL_CANDIDATE_HEADER + candidate
            if relative == verifier.CANDIDATE_WORKFLOW_FIXTURE
            else b"regular\n"
        )
        path.write_bytes(payload)
    unsafe = (tmp_path / unsafe_relative).resolve()
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self == unsafe or original_is_symlink(self),
    )
    monkeypatch.setattr(
        verifier._BASE,
        "_git_bytes",
        lambda *_args: candidate,
    )
    monkeypatch.setattr(
        verifier._BASE,
        "verify_repository_evidence",
        lambda *_args: b"old manifest",
    )

    with pytest.raises(verifier.PublicReleaseVerificationError, match="missing or unsafe"):
        verifier.verify_repository_evidence(tmp_path, verifier.expected_evidence())


def test_exact_attempt_scoped_authority_jobs_are_accepted() -> None:
    verifier.validate_release_workflow(
        _run(),
        _jobs(),
        verifier.expected_evidence()["release_workflow"],
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"run_attempt": 1}, "run_attempt"),
        ({"head_sha": "0" * 40}, "head_sha"),
        ({"event": "push"}, "event"),
        ({"conclusion": "failure"}, "conclusion"),
        ({"head_repository": {"full_name": "example/fork"}}, "head_repository"),
    ],
)
def test_release_run_identity_is_exact(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(verifier.PublicReleaseVerificationError, match=message):
        verifier.validate_release_workflow(
            _run(**overrides),
            _jobs(),
            verifier.expected_evidence()["release_workflow"],
        )


def test_rejects_old_success_run_with_unexpanded_skipped_public_matrix() -> None:
    jobs = _jobs()
    values = [
        item
        for item in jobs["jobs"]
        if not str(item["name"]).startswith("Public PyPI verify /")
    ]
    values.append(
        _job(
            verifier.RELEASE_RUN_ID + 200,
            "Public PyPI verify / ${{ matrix.os }} / Python ${{ matrix.python-version }}",
            "skipped",
        )
    )

    with pytest.raises(verifier.PublicReleaseVerificationError, match="placeholder"):
        verifier.validate_release_workflow(
            _run(),
            {"total_count": len(values), "jobs": values},
            verifier.expected_evidence()["release_workflow"],
        )


def test_rejects_skipped_authority_job_even_when_run_is_success() -> None:
    jobs = _jobs()
    authority = next(
        item
        for item in jobs["jobs"]
        if item["name"] == "Fresh-read and verify exact PyPI files"
    )
    authority["conclusion"] = "skipped"

    with pytest.raises(verifier.PublicReleaseVerificationError, match="unexpected skipped"):
        verifier.validate_release_workflow(
            _run(),
            jobs,
            verifier.expected_evidence()["release_workflow"],
        )


def test_rejects_duplicate_or_incomplete_attempt_scoped_jobs() -> None:
    duplicate = _jobs()
    duplicate["jobs"].append(deepcopy(duplicate["jobs"][0]))
    duplicate["total_count"] = len(duplicate["jobs"])
    with pytest.raises(verifier.PublicReleaseVerificationError, match="duplicate"):
        verifier.validate_release_workflow(
            _run(),
            duplicate,
            verifier.expected_evidence()["release_workflow"],
        )

    incomplete = _jobs()
    incomplete["total_count"] = len(incomplete["jobs"]) + 1
    with pytest.raises(verifier.PublicReleaseVerificationError, match="incomplete"):
        verifier.validate_release_workflow(
            _run(),
            incomplete,
            verifier.expected_evidence()["release_workflow"],
        )


def test_phase_e_manifest_is_an_exact_same_position_transition() -> None:
    verifier.validate_required_workflow_transition(_old_manifest(), _new_manifest())


def test_phase_e_manifest_rejects_any_second_change() -> None:
    payload = json.loads(_new_manifest())
    payload["required_workflows"][0]["name"] = "Changed too"
    changed = (json.dumps(payload, indent=2) + "\n").encode()

    with pytest.raises(verifier.PublicReleaseVerificationError, match="exactly one"):
        verifier.validate_required_workflow_transition(_old_manifest(), changed)


def test_phase_e_manifest_rejects_wrong_count_or_position() -> None:
    payload = json.loads(_new_manifest())
    payload["required_workflows"].pop()
    short = (json.dumps(payload, indent=2) + "\n").encode()
    with pytest.raises(verifier.PublicReleaseVerificationError, match="48 entries"):
        verifier.validate_required_workflow_transition(_old_manifest(), short)

    payload = json.loads(_new_manifest())
    payload["required_workflows"][46], payload["required_workflows"][47] = (
        payload["required_workflows"][47],
        payload["required_workflows"][46],
    )
    moved = (json.dumps(payload, indent=2) + "\n").encode()
    with pytest.raises(verifier.PublicReleaseVerificationError, match="same-position"):
        verifier.validate_required_workflow_transition(_old_manifest(), moved)


def test_pypi_metadata_binds_description_python_range_and_exact_files() -> None:
    evidence = verifier.expected_evidence()
    assert verifier.validate_pypi_metadata(_pypi(), evidence)["info"]["version"] == "2.2.1"

    wrong_content_type = _pypi()
    wrong_content_type["info"]["description_content_type"] = "text/plain"
    with pytest.raises(verifier.PublicReleaseVerificationError, match="content_type"):
        verifier.validate_pypi_metadata(wrong_content_type, evidence)

    yanked = _pypi()
    yanked["urls"][0]["yanked"] = True
    with pytest.raises(verifier.PublicReleaseVerificationError, match="yanked"):
        verifier.validate_pypi_metadata(yanked, evidence)

    extra = _pypi()
    extra["urls"].append(
        {
            "filename": "swirengine-2.2.1-extra.whl",
            "url": "https://files.pythonhosted.org/packages/extra",
            "yanked": False,
        }
    )
    with pytest.raises(verifier.PublicReleaseVerificationError, match="exact three"):
        verifier.validate_pypi_metadata(extra, evidence)


def test_pypi_and_github_distribution_bytes_must_be_identical() -> None:
    pypi = _pypi()
    github_bytes = {
        name: name.encode("utf-8") for name in verifier.EXPECTED_DISTRIBUTION_NAMES
    }

    verifier._verify_pypi_bytes(
        pypi,
        github_bytes,
        request_bytes=lambda url: Path(url).name.encode("utf-8"),
    )

    with pytest.raises(verifier.PublicReleaseVerificationError, match="bytes differ"):
        verifier._verify_pypi_bytes(
            pypi,
            github_bytes,
            request_bytes=lambda _url: b"tampered",
        )


def test_public_install_does_not_expose_repository_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append({"args": args, "kwargs": kwargs})
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setenv("GH_TOKEN", "secret-gh")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-actions")
    monkeypatch.setenv("PYTHONPATH", "unsafe-source-tree")
    monkeypatch.setenv("PYTHONHOME", "unsafe-python-home")
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.invalid/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://example.invalid/extra")
    monkeypatch.setenv("PIP_CONFIG_FILE", "unsafe-pip.ini")
    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    verifier.verify_public_install()

    assert len(calls) == 3
    for call in calls:
        environment = call["kwargs"]["env"]
        normalized_names = {name.upper() for name in environment}
        assert "GH_TOKEN" not in normalized_names
        assert "GITHUB_TOKEN" not in normalized_names
        assert "PYTHONHOME" not in normalized_names
        assert "PYTHONPATH" not in normalized_names
        assert not any(name.startswith("PIP_") for name in normalized_names)
        assert environment["PYTHONNOUSERSITE"] == "1"
    install_command = calls[1]["args"][0]
    assert install_command[:5] == [
        install_command[0],
        "-m",
        "pip",
        "--isolated",
        "install",
    ]
    assert "--index-url" in install_command
    assert "https://pypi.org/simple" in install_command
    assert "--no-input" in install_command
    assert "swirengine==2.2.1" in install_command


def test_cli_exposes_only_the_three_phase_e_controls() -> None:
    parser = verifier._parser()
    destinations = {action.dest for action in parser._actions}

    assert destinations == {"help", "root", "evidence", "skip_install"}
    args = parser.parse_args([])
    assert args.evidence == verifier.DEFAULT_EVIDENCE
    assert args.skip_install is False
