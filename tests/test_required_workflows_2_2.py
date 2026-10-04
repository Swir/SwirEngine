from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verify_required_workflows_2_2 import (
    DEFAULT_MANIFEST,
    EXPECTED_REPOSITORY,
    RequiredWorkflow,
    RequiredWorkflowManifest,
    WorkflowVerificationError,
    load_manifest,
    parse_manifest,
    verify_manifest_files,
    verify_workflow_runs,
)

ROOT = Path(__file__).resolve().parents[1]
HEAD_SHA = "a" * 40


def _run(
    workflow: RequiredWorkflow,
    *,
    event: str = "pull_request",
    head_sha: str = HEAD_SHA,
    repository: str = EXPECTED_REPOSITORY,
    head_repository: str = EXPECTED_REPOSITORY,
    name: str | None = None,
    status: str = "completed",
    conclusion: str = "success",
    run_number: int = 1,
    run_attempt: int = 1,
    run_id: int = 1,
) -> dict[str, object]:
    return {
        "path": workflow.path,
        "name": workflow.name if name is None else name,
        "head_sha": head_sha,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "repository": {"full_name": repository},
        "head_repository": {"full_name": head_repository},
        "run_number": run_number,
        "run_attempt": run_attempt,
        "id": run_id,
    }


def _payload(runs: list[dict[str, object]]) -> dict[str, object]:
    return {"total_count": len(runs), "workflow_runs": runs}


@pytest.fixture(scope="module")
def manifest() -> RequiredWorkflowManifest:
    return load_manifest(ROOT / DEFAULT_MANIFEST)


def test_repository_manifest_tracks_the_explicit_candidate_workflows(
    manifest: RequiredWorkflowManifest,
) -> None:
    verified = verify_manifest_files(manifest, ROOT)

    assert manifest.repository == EXPECTED_REPOSITORY
    assert len(verified) == 47
    assert len({workflow.path for workflow in verified}) == 47
    assert len({workflow.name for workflow in verified}) == 47
    assert RequiredWorkflow(
        path=".github/workflows/release-candidate-2.2.yml",
        name="SwirEngine 2.2 Release Candidate",
    ) in verified
    assert all(workflow.path != ".github/workflows/release-readiness-2.2.yml" for workflow in verified)


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/content-build-1-9.yml",
        ".github/workflows/desktop-shipping-1-9.yml",
        ".github/workflows/editor-vfx-2-2.yml",
        ".github/workflows/game-state-production-1-9.yml",
        ".github/workflows/real-game-production-1-9.yml",
        ".github/workflows/runtime-diagnostics-1-9.yml",
        ".github/workflows/scene-packages-1-9.yml",
    ],
)
def test_candidate_version_change_triggers_every_previously_uncovered_workflow(
    workflow_path: str,
) -> None:
    import yaml

    workflow = yaml.load((ROOT / workflow_path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(workflow, dict)
    assert "pyproject.toml" in workflow["on"]["pull_request"]["paths"]


@pytest.mark.parametrize("mode,event", [("pull-request", "pull_request"), ("push", "push")])
def test_exact_sha_success_requires_every_manifest_workflow(
    manifest: RequiredWorkflowManifest,
    mode: str,
    event: str,
) -> None:
    runs = [_run(workflow, event=event) for workflow in manifest.workflows]

    report = verify_workflow_runs(manifest, _payload(runs), head_sha=HEAD_SHA, mode=mode)

    assert report.event == event
    assert report.head_sha == HEAD_SHA
    assert report.verified == manifest.workflows


def test_opposite_event_does_not_satisfy_selected_mode(
    manifest: RequiredWorkflowManifest,
) -> None:
    runs = [_run(workflow, event="push") for workflow in manifest.workflows]

    with pytest.raises(WorkflowVerificationError, match="missing pull_request run"):
        verify_workflow_runs(manifest, _payload(runs), head_sha=HEAD_SHA, mode="pull-request")


def test_missing_required_workflow_fails_closed(manifest: RequiredWorkflowManifest) -> None:
    runs = [_run(workflow) for workflow in manifest.workflows[:-1]]

    with pytest.raises(WorkflowVerificationError, match="missing pull_request run"):
        verify_workflow_runs(manifest, _payload(runs), head_sha=HEAD_SHA, mode="pull-request")


def test_latest_required_workflow_rerun_is_authoritative(
    manifest: RequiredWorkflowManifest,
) -> None:
    runs = [_run(workflow) for workflow in manifest.workflows]
    runs[0] = _run(
        manifest.workflows[0],
        status="completed",
        conclusion="failure",
        run_number=20,
        run_attempt=1,
        run_id=100,
    )
    runs.append(
        _run(
            manifest.workflows[0],
            run_number=20,
            run_attempt=2,
            run_id=100,
        )
    )

    report = verify_workflow_runs(
        manifest,
        _payload(runs),
        head_sha=HEAD_SHA,
        mode="pull-request",
    )

    assert report.verified == manifest.workflows


def test_latest_required_workflow_rerun_after_first_page_is_authoritative(
    manifest: RequiredWorkflowManifest,
) -> None:
    runs: list[dict[str, object]] = []
    for run_number in range(1, 4):
        for index, workflow in enumerate(manifest.workflows):
            runs.append(
                _run(
                    workflow,
                    status="completed",
                    conclusion="failure" if workflow == manifest.workflows[0] else "success",
                    run_number=run_number,
                    run_id=run_number * 1000 + index,
                )
            )
    assert len(runs) > 100
    runs.append(
        _run(
            manifest.workflows[0],
            run_number=4,
            run_id=4000,
        )
    )

    report = verify_workflow_runs(
        manifest,
        _payload(runs),
        head_sha=HEAD_SHA,
        mode="pull-request",
    )

    assert report.verified == manifest.workflows


def test_ambiguous_duplicate_required_workflow_fails_closed(
    manifest: RequiredWorkflowManifest,
) -> None:
    runs = [_run(workflow) for workflow in manifest.workflows]
    runs.append(_run(manifest.workflows[0]))

    with pytest.raises(WorkflowVerificationError, match="ambiguous duplicate"):
        verify_workflow_runs(manifest, _payload(runs), head_sha=HEAD_SHA, mode="pull-request")


def test_unexpected_name_for_required_path_fails_closed(
    manifest: RequiredWorkflowManifest,
) -> None:
    runs = [_run(workflow) for workflow in manifest.workflows]
    runs[0] = _run(manifest.workflows[0], name="Renamed without manifest update")

    with pytest.raises(WorkflowVerificationError, match="unexpected workflow name"):
        verify_workflow_runs(manifest, _payload(runs), head_sha=HEAD_SHA, mode="pull-request")


@pytest.mark.parametrize(
    ("status", "conclusion", "message"),
    [
        ("in_progress", "", "not completed"),
        ("completed", "failure", "did not conclude successfully"),
    ],
)
def test_non_green_required_workflow_fails_closed(
    manifest: RequiredWorkflowManifest,
    status: str,
    conclusion: str,
    message: str,
) -> None:
    runs = [_run(workflow) for workflow in manifest.workflows]
    runs[0] = _run(manifest.workflows[0], status=status, conclusion=conclusion)

    with pytest.raises(WorkflowVerificationError, match=message):
        verify_workflow_runs(manifest, _payload(runs), head_sha=HEAD_SHA, mode="pull-request")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"head_sha": "b" * 40}, "unexpected head SHA"),
        ({"repository": "someone/fork"}, "unexpected repository"),
        ({"head_repository": "someone/fork"}, "unexpected head repository"),
    ],
)
def test_foreign_run_identity_fails_closed(
    manifest: RequiredWorkflowManifest,
    override: dict[str, str],
    message: str,
) -> None:
    runs = [_run(workflow) for workflow in manifest.workflows]
    runs[0] = _run(manifest.workflows[0], **override)

    with pytest.raises(WorkflowVerificationError, match=message):
        verify_workflow_runs(manifest, _payload(runs), head_sha=HEAD_SHA, mode="pull-request")


def test_incomplete_paginated_payload_fails_closed(manifest: RequiredWorkflowManifest) -> None:
    runs = [_run(workflow) for workflow in manifest.workflows]
    payload = {"total_count": len(runs) + 1, "workflow_runs": runs}

    with pytest.raises(WorkflowVerificationError, match="payload is incomplete"):
        verify_workflow_runs(manifest, payload, head_sha=HEAD_SHA, mode="pull-request")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"schema_version": 2}, "schema_version must be 1"),
        ({"repository": "someone/fork"}, "repository must be Swir/SwirEngine"),
    ],
)
def test_manifest_identity_is_versioned_and_repository_bound(
    mutation: dict[str, object],
    message: str,
) -> None:
    data = json.loads((ROOT / DEFAULT_MANIFEST).read_text(encoding="utf-8"))
    data.update(mutation)

    with pytest.raises(WorkflowVerificationError, match=message):
        parse_manifest(data)


@pytest.mark.parametrize("duplicate_field", ["path", "name"])
def test_manifest_rejects_duplicate_workflow_identity(duplicate_field: str) -> None:
    data = json.loads((ROOT / DEFAULT_MANIFEST).read_text(encoding="utf-8"))
    data["required_workflows"][1][duplicate_field] = data["required_workflows"][0][
        duplicate_field
    ]

    with pytest.raises(WorkflowVerificationError, match=f"duplicate required workflow {duplicate_field}"):
        parse_manifest(data)


def test_local_workflow_name_drift_fails_closed(tmp_path: Path) -> None:
    workflow_path = tmp_path / ".github/workflows/gate.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("name: Renamed Gate\non:\n  pull_request:\n", encoding="utf-8")
    manifest = RequiredWorkflowManifest(
        repository=EXPECTED_REPOSITORY,
        workflows=(
            RequiredWorkflow(path=".github/workflows/gate.yml", name="Expected Gate"),
        ),
    )

    with pytest.raises(WorkflowVerificationError, match="unexpected workflow name"):
        verify_manifest_files(manifest, tmp_path)
