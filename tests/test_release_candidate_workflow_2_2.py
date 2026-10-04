from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "tests/fixtures/release-candidate-2.2.yml"
EXPECTED_SOURCE_EXPRESSION = "${{ github.event.pull_request.head.sha }}"


def _workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return text, parsed


def test_historical_candidate_workflow_is_same_repo_pull_request_only_and_read_only() -> None:
    text, workflow = _workflow()

    assert workflow["name"] == "SwirEngine 2.2 Release Candidate"
    assert workflow["on"].keys() == {"pull_request"}
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["env"]["EXPECTED_SOURCE_SHA"] == EXPECTED_SOURCE_EXPRESSION
    assert "workflow_dispatch" not in text
    assert "id-token: write" not in text
    assert "contents: write" not in text
    assert "pypa/gh-action-pypi-publish" not in text
    assert "twine upload" not in text
    assert "gh release" not in text
    assert "git push" not in text


def test_historical_candidate_workflow_binds_exact_same_repo_branch_and_head() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]
    assert set(jobs) == {"candidate-contract", "clean-install-matrix", "candidate-evidence"}

    required_guard = (
        'test "$GITHUB_EVENT_NAME" = "pull_request"',
        "EXPECTED_REPOSITORY: Swir/SwirEngine",
        "EXPECTED_HEAD_BRANCH: release/2.2.0-candidate",
        "EXPECTED_BASE_BRANCH: main",
        "'.pull_request.head.repo.full_name'",
        "'.pull_request.base.repo.full_name'",
        "'.pull_request.head.ref'",
        "'.pull_request.base.ref'",
        "'.pull_request.head.sha'",
        'test -f "$GITHUB_EVENT_PATH"',
    )
    for fragment in required_guard:
        assert fragment in text
    assert "github.event_path" not in text

    checkout_count = 0
    for job in jobs.values():
        for step in job["steps"]:
            if step.get("uses") == "actions/checkout@v4":
                checkout_count += 1
                assert step["with"]["ref"] == "${{ env.EXPECTED_SOURCE_SHA }}"
                assert step["with"]["persist-credentials"] == "false"
    assert checkout_count == 3
    assert text.count("git rev-parse HEAD") == 3
    assert jobs["clean-install-matrix"]["needs"] == "candidate-contract"
    assert jobs["candidate-evidence"]["needs"] == [
        "candidate-contract",
        "clean-install-matrix",
    ]


def test_candidate_workflow_builds_three_exact_distributions_and_fifteen_cells() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]
    candidate = jobs["candidate-contract"]
    matrix = jobs["clean-install-matrix"]["strategy"]["matrix"]

    assert matrix["os"] == ["ubuntu-latest", "windows-latest", "macos-latest"]
    assert matrix["python-version"] == ["3.10", "3.11", "3.12", "3.13", "3.14"]
    assert len(matrix["os"]) * len(matrix["python-version"]) == 15
    assert "env" not in candidate
    build = next(
        step
        for step in candidate["steps"]
        if step.get("name") == "Build exact-source portable wheel and sdist"
    )
    cache_route = next(
        step
        for step in candidate["steps"]
        if step.get("name") == "Route Python caches outside the candidate source tree"
    )
    assert cache_route["run"] == (
        'echo "PYTHONPYCACHEPREFIX=$RUNNER_TEMP/candidate-pycache" >> "$GITHUB_ENV"'
    )
    assert candidate["steps"].index(cache_route) < candidate["steps"].index(build)
    assert "env" not in build
    assert (
        'python -m build --wheel --sdist --outdir "$RUNNER_TEMP/candidate-portable"'
        in build["run"]
    )
    assert build["run"].count("status --porcelain --untracked-files=all") == 2
    assert build["run"].count("status --short --untracked-files=all") == 2
    assert "--outdir dist" not in build["run"]
    assert "python -m pytest -q -p no:cacheprovider" in text
    assert "python -m ruff check --no-cache" in text
    upload = next(
        step
        for step in candidate["steps"]
        if step.get("uses") == "actions/upload-artifact@v4"
    )
    assert upload["with"]["path"] == (
        "${{ runner.temp }}/candidate-portable/swirengine-2.2.0-py3-none-any.whl\n"
        "${{ runner.temp }}/candidate-portable/swirengine-2.2.0.tar.gz\n"
    )
    assert "tools/build_vendored_wheel.py" in text
    for distribution in (
        "swirengine-2.2.0-py3-none-any.whl",
        "swirengine-2.2.0-cp314-cp314-win_amd64.whl",
        "swirengine-2.2.0.tar.gz",
    ):
        assert distribution in text
    assert text.count("--expected-version 2.2.0") == 2
    assert "--require-vendored-native" in text
    assert "--wheel-only" in text
    assert "--verify-cli21" in text


def test_candidate_workflow_generates_exact_head_evidence_and_retains_it_seven_days() -> None:
    text, workflow = _workflow()
    uploads = [
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("uses") == "actions/upload-artifact@v4"
    ]

    assert len(uploads) == 3
    assert all(upload["with"]["retention-days"] == "7" for upload in uploads)
    assert text.count("python tools/candidate_evidence_2_2.py") == 2
    assert "candidate_evidence_2_2.py generate" in text
    assert "candidate_evidence_2_2.py verify" in text
    assert '--source-sha "$EXPECTED_SOURCE_SHA"' in text
    assert "--workflow-manifest .github/release-gates/2.2-required-workflows.json" in text
    assert "dist/SHA256SUMS" in text
    assert "dist/candidate-provenance.json" in text


def test_candidate_workflow_runs_candidate_contract_and_focused_regressions() -> None:
    text, _ = _workflow()

    required = (
        "python tools/verify_2_2_release_candidate.py",
        "python tools/verify_2_2_release_readiness.py",
        "python tools/verify_required_workflows_2_2.py",
        "python tools/verify_distribution_audit_data_2_2.py",
        '--dist-dir "$RUNNER_TEMP/candidate-portable"',
        "tests/test_verify_2_2_release_candidate.py",
        "tests/test_candidate_merge_2_2.py",
        "tests/test_reconcile_release_2_2.py",
        "tests/test_release_workflow_2_2.py",
        "tests/test_candidate_evidence_2_2.py",
        "tests/test_release_candidate_workflow_2_2.py",
        "tests/test_required_workflows_2_2.py",
        "tests/test_sdist_identity_2_2.py",
        "tests/test_vendored_wheel.py",
    )
    for fragment in required:
        assert fragment in text
