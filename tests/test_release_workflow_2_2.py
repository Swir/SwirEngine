from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/release.yml"
PUBLICATION_GATE_PATH = ROOT / ".github/workflows/publication-gate-2.2.yml"
READINESS_PATH = ROOT / ".github/workflows/release-readiness-2.2.yml"


def _workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return text, parsed


def _publication_gate() -> tuple[str, dict[str, object]]:
    text = PUBLICATION_GATE_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return text, parsed


def test_workflow_display_names_are_repository_unique() -> None:
    names: dict[str, Path] = {}
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        parsed = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        assert isinstance(parsed, dict)
        name = parsed.get("name")
        assert isinstance(name, str) and name
        assert name not in names, f"duplicate workflow name {name!r}: {names[name]} and {path}"
        names[name] = path


def test_yaml_contract_dependency_is_available_to_every_full_test_run() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readiness = READINESS_PATH.read_text(encoding="utf-8")

    assert 'dev = ["pytest>=8,<10", "ruff>=0.16,<0.17", "PyYAML>=6,<7"]' in project
    assert '"PyYAML>=6,<7"' in readiness


def test_release_identity_waits_for_the_publication_gate_workflow() -> None:
    _, workflow = _workflow()
    triggers = workflow["on"]

    assert isinstance(triggers, dict)
    assert set(triggers) == {"workflow_run"}
    assert triggers["workflow_run"] == {
        "workflows": ["SwirEngine 2.2 Publication Gate"],
        "types": ["completed"],
    }
    assert workflow["name"] == "Release"


def test_publication_gate_is_read_only_and_marker_push_only() -> None:
    text, workflow = _publication_gate()
    assert workflow["name"] == "SwirEngine 2.2 Publication Gate"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"] == {
        "push": {
            "branches": ["release/2.2.0-publication"],
            "paths": [".release/publish-2.2.0/publication.json"],
        }
    }
    assert "id-token: write" not in text
    assert "contents: write" not in text
    assert "tools/verify_publication_chain_2_2.py" in text
    assert "tools/verify_2_2_release_candidate.py" in text


def test_release_requires_exact_trigger_and_two_marker_chain() -> None:
    text, _ = _workflow()

    required = (
        'test "$GITHUB_REPOSITORY" = "$EXPECTED_REPOSITORY"',
        'test "$GITHUB_EVENT_NAME" = "workflow_run"',
        "'.workflow_run.event'",
        "'.workflow_run.path'",
        "'.workflow_run.conclusion'",
        "'.workflow_run.head_repository.full_name'",
        "'.workflow_run.head_branch'",
        "'.workflow_run.head_sha'",
        'test "$remote_tag" = "$PUBLICATION_SHA"',
        "trusted-verifier/tools/verify_publication_chain_2_2.py",
        "trusted-verifier/tools/verify_candidate_merge_2_2.py",
        "--tag-policy absent-or-publication",
        "--tag-policy publication",
    )
    for fragment in required:
        assert fragment in text


def test_release_bootstraps_provenance_from_trusted_workflow_source() -> None:
    _, workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    chain = jobs["publication-chain"]
    assert isinstance(chain, dict)
    steps = chain["steps"]
    assert isinstance(steps, list)

    trusted = steps[0]
    target = steps[1]
    assert trusted["uses"] == "actions/checkout@v4"
    assert trusted["with"] == {
        "ref": "${{ github.workflow_sha }}",
        "persist-credentials": "false",
        "path": "trusted-verifier",
    }
    assert target["uses"] == "actions/checkout@v4"
    assert target["with"] == {
        "ref": "${{ github.event.workflow_run.head_sha }}",
        "fetch-depth": "0",
        "persist-credentials": "false",
        "path": "publication-source",
    }

    chain_run = next(step["run"] for step in steps if step.get("id") == "chain")
    assert "python trusted-verifier/tools/verify_publication_chain_2_2.py" in chain_run
    assert "--root publication-source" in chain_run
    merge_run = next(step["run"] for step in steps if "candidate pull request" in step.get("name", ""))
    assert "python trusted-verifier/tools/verify_candidate_merge_2_2.py" in merge_run
    assert "--root publication-source" in merge_run
    assert "python publication-source/" not in str(steps)


def test_named_exact_sha_workflow_gate_replaces_counting() -> None:
    text, _ = _workflow()

    assert "verify_required_workflows_2_2.py" in text
    assert '--sha "$CANDIDATE_SOURCE_SHA"' in text
    assert "--mode pull-request" in text
    assert "head_sha=${CANDIDATE_SOURCE_SHA}&event=pull_request" in text
    assert "gh api --paginate --slurp" in text
    assert "required-run-pages.json" in text
    assert "total_count: .[0].total_count" in text
    assert "workflow_runs: [.[].workflow_runs[]]" in text
    assert "EXPECTED_PR_WORKFLOWS" not in text
    assert "count -ge" not in text


def test_release_builds_both_sdists_and_binds_provenance_v2() -> None:
    text, _ = _workflow()

    required = (
        'git worktree add --detach candidate-tree "$CANDIDATE_SOURCE_SHA"',
        "tools/verify_sdist_identity_2_2.py",
        "--candidate candidate-dist/swirengine-2.2.0.tar.gz",
        "--publication publication-dist/swirengine-2.2.0.tar.gz",
        "tools/release_evidence_2_2.py",
        '--candidate-source-commit "$CANDIDATE_SOURCE_SHA"',
        '--candidate-marker-commit "$CANDIDATE_MARKER_SHA"',
        '--publication-commit "$PUBLICATION_SHA"',
        '--expected-workflow-manifest-sha256 "$WORKFLOW_MANIFEST_SHA256"',
        '--expected-logical-sdist-sha256 "$LOGICAL_SDIST_SHA256"',
    )
    for fragment in required:
        assert fragment in text


def test_retries_reconcile_fresh_state_and_never_clobber() -> None:
    text, _ = _workflow()

    assert text.count("tools/reconcile_release_2_2.py") >= 7
    assert text.count("--initial-pypi-json") >= 4
    assert text.count("--initial-tag-json") >= 4
    assert text.count("--initial-release-json") >= 4
    assert "--require-complete" in text
    assert "skip-existing" not in text
    assert "--clobber" not in text
    assert "git push --force" not in text
    assert "git tag -f" not in text
    assert text.count('refs/heads/$PUBLICATION_BRANCH') >= 4


def test_trusted_publisher_identity_and_minimal_write_permissions_are_preserved() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)

    pypi = jobs["pypi-publish"]
    assert pypi["environment"] == "pypi"
    assert pypi["permissions"] == {"contents": "read", "id-token": "write"}
    assert "pypa/gh-action-pypi-publish@release/v1" in text
    assert jobs["ensure-tag"]["permissions"] == {"contents": "write"}
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    assert workflow["permissions"] == {"contents": "read"}


def test_release_assets_are_never_built_from_public_registry_state() -> None:
    text, _ = _workflow()

    assert 'ref: ${{ needs.publication-chain.outputs.publication_sha }}' in text
    assert "swirengine==2.2.0" in text
    assert "--index-url https://pypi.org/simple" in text
    assert "--expected-version 2.2.0" in text
    assert "refs/tags/v2.1.0" not in text
