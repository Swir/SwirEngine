from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/release.yml"
PUBLICATION_GATE_PATH = ROOT / ".github/workflows/publication-gate-2.2.yml"
CANDIDATE_PATH = ROOT / ".github/workflows/release-candidate-2.2.yml"
CHECKOUT_ACTION = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
DOWNLOAD_ACTION = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
PYPI_ACTION = (
    "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
)


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
    candidate = CANDIDATE_PATH.read_text(encoding="utf-8")

    assert 'dev = ["pytest>=8,<10", "ruff>=0.16,<0.17", "PyYAML>=6,<7"]' in project
    assert '"PyYAML>=6,<7"' in candidate


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
    for step in workflow["jobs"]["publication-chain"]["steps"]:
        uses = step.get("uses")
        if uses is not None:
            revision = uses.rpartition("@")[2]
            assert len(revision) == 40
            assert set(revision) <= set("0123456789abcdef")


def test_release_requires_exact_trigger_and_two_marker_chain() -> None:
    text, _ = _workflow()

    required = (
        'test "$GITHUB_REPOSITORY" = "$EXPECTED_REPOSITORY"',
        'test "$GITHUB_EVENT_NAME" = "workflow_run"',
        (
            'test "$TRUSTED_WORKFLOW_REF" = '
            '"$EXPECTED_REPOSITORY/.github/workflows/release.yml@refs/heads/main"'
        ),
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
    assert trusted["uses"] == CHECKOUT_ACTION
    assert trusted["with"] == {
        "ref": "${{ github.workflow_sha }}",
        "persist-credentials": "false",
        "path": "trusted-verifier",
    }
    assert target["uses"] == CHECKOUT_ACTION
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
    assert text.count("git/ref/heads/${PUBLICATION_BRANCH}") >= 5


def test_trusted_publisher_identity_and_minimal_write_permissions_are_preserved() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)

    pypi = jobs["pypi-publish"]
    assert pypi["environment"] == "pypi"
    assert pypi["permissions"] == {"id-token": "write"}
    assert pypi["needs"] == "prepare-pypi"
    assert pypi["if"] == "needs.prepare-pypi.outputs.upload == 'true'"
    assert len(pypi["steps"]) == 2
    assert [step["uses"] for step in pypi["steps"]] == [DOWNLOAD_ACTION, PYPI_ACTION]
    assert all("run" not in step for step in pypi["steps"])
    assert "actions/checkout" not in str(pypi)

    prepare = jobs["prepare-pypi"]
    verify = jobs["verify-pypi"]
    assert prepare["permissions"] == {"contents": "read"}
    assert verify["permissions"] == {"contents": "read"}
    assert "id-token" not in str(prepare.get("permissions"))
    assert "id-token" not in str(verify.get("permissions"))
    assert jobs["prepare-github-release"]["needs"] == [
        "publication-chain",
        "release-evidence",
        "verify-tag",
    ]
    assert jobs["prepare-pypi"]["needs"] == [
        "publication-chain",
        "release-evidence",
        "verify-github-release",
    ]
    assert jobs["post-release-public-pypi"]["needs"] == [
        "publication-chain",
        "verify-pypi",
    ]
    assert text.count("id-token: write") == 1
    assert "pypa/gh-action-pypi-publish@release/v1" not in text
    assert jobs["ensure-tag"]["permissions"] == {"contents": "write"}
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    assert workflow["permissions"] == {"contents": "read"}


def test_write_jobs_are_minimal_and_never_execute_candidate_code() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]

    assert text.count("contents: write") == 2
    assert jobs["ensure-tag"]["permissions"] == {"contents": "write"}
    assert jobs["github-release"]["permissions"] == {"contents": "write"}

    ensure_tag = jobs["ensure-tag"]
    assert len(ensure_tag["steps"]) == 1
    assert "run" in ensure_tag["steps"][0]
    assert "python" not in ensure_tag["steps"][0]["run"]
    assert "actions/checkout" not in str(ensure_tag)

    github_release = jobs["github-release"]
    assert len(github_release["steps"]) == 2
    assert github_release["steps"][0]["uses"] == DOWNLOAD_ACTION
    assert "run" in github_release["steps"][1]
    assert "python" not in github_release["steps"][1]["run"]
    assert "actions/checkout" not in str(github_release)
    assert "gh release upload" not in text


def test_github_release_requires_server_immutability_and_attestations() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]

    assert "gh release verify \"$RELEASE_TAG\"" in text
    assert "gh release verify-asset \"$RELEASE_TAG\"" in text
    assert "--notes-file github-release-input/RELEASE_NOTES_2_2.md" in text
    assert text.count("--release-notes release-input/RELEASE_NOTES_2_2.md") == 6
    assert jobs["verify-github-release"]["permissions"] == {
        "attestations": "read",
        "contents": "read",
    }

    evidence_upload = next(
        step
        for step in jobs["release-evidence"]["steps"]
        if step.get("with", {}).get("name") == "swirengine-2.2.0-publication-assets"
    )
    assert set(evidence_upload["with"]["path"].splitlines()) == {
        "dist/*",
        "initial-state/*.json",
        "RELEASE_NOTES_2_2.md",
    }

    create_run = jobs["github-release"]["steps"][1]["run"]
    for name in (
        "swirengine-2.2.0-py3-none-any.whl",
        "swirengine-2.2.0-cp314-cp314-win_amd64.whl",
        "swirengine-2.2.0.tar.gz",
        "SHA256SUMS",
        "release-provenance.json",
    ):
        assert create_run.count(f"github-release-input/{name}") == 1
    assert "github-release-input/*" not in create_run
    assert "--draft" not in create_run
    assert '--title "SwirEngine 2.2.0"' in create_run
    assert "--notes-file github-release-input/RELEASE_NOTES_2_2.md" in create_run


def test_release_workflow_pins_every_reusable_action_to_a_full_commit() -> None:
    _, workflow = _workflow()

    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            uses = step.get("uses")
            if uses is None:
                continue
            owner_action, separator, revision = uses.rpartition("@")
            assert separator == "@", owner_action
            assert len(revision) == 40, uses
            assert set(revision) <= set("0123456789abcdef"), uses


def test_release_assets_are_never_built_from_public_registry_state() -> None:
    text, _ = _workflow()

    assert 'ref: ${{ needs.publication-chain.outputs.publication_sha }}' in text
    assert "swirengine==2.2.0" in text
    assert "--index-url https://pypi.org/simple" in text
    assert "--expected-version 2.2.0" in text
    assert "refs/tags/v2.1.0" not in text
