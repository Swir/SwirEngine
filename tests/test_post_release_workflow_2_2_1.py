from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/post-release-2.2.1.yml"
CHECKOUT_ACTION = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON_ACTION = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
EXPECTED_SOURCE = "${{ github.event.pull_request.head.sha || github.sha }}"


def _workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return text, parsed


def _assert_actions_are_commit_pinned(document: object) -> None:
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "uses":
                assert isinstance(value, str)
                assert re.fullmatch(r".+@[0-9a-f]{40}", value)
            _assert_actions_are_commit_pinned(value)
    elif isinstance(document, list):
        for value in document:
            _assert_actions_are_commit_pinned(value)


def test_post_release_workflow_has_exact_identity_triggers_and_permissions() -> None:
    text, workflow = _workflow()

    assert workflow["name"] == "Post-release 2.2.1 Public Verification"
    assert set(workflow["on"]) == {"pull_request", "push"}
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["pull_request"]["paths"] == workflow["on"]["push"]["paths"]
    paths = workflow["on"]["pull_request"]["paths"]
    for required in (
        ".gitattributes",
        "release-evidence/2.2.1/**",
        ".github/release-gates/2.2.1-required-workflows.json",
        ".github/workflows/release-candidate-2.2.1.yml",
        ".github/workflows/post-release-2.2.1.yml",
        "tests/fixtures/release-candidate-2.2.1.yml",
    ):
        assert required in paths
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert workflow["env"] == {"EXPECTED_SOURCE_SHA": EXPECTED_SOURCE}
    assert "workflow_dispatch" not in text
    assert "pull_request_target" not in text
    for forbidden in (
        "contents: write",
        "id-token: write",
        "pypa/gh-action-pypi-publish",
        "twine upload",
        "gh release create",
        "git push",
    ):
        assert forbidden not in text
    _assert_actions_are_commit_pinned(workflow)


def test_post_release_workflow_checks_out_exact_head_with_full_history() -> None:
    _, workflow = _workflow()

    jobs = workflow["jobs"]
    assert set(jobs) == {"contract", "public-install"}
    checkout_count = 0
    for job in jobs.values():
        checkout = next(step for step in job["steps"] if step.get("uses") == CHECKOUT_ACTION)
        checkout_count += 1
        assert checkout["with"] == {
            "ref": EXPECTED_SOURCE,
            "fetch-depth": "0",
            "persist-credentials": "false",
        }
        assert any("git rev-parse HEAD" in step.get("run", "") for step in job["steps"])
    assert checkout_count == 2


def test_post_release_contract_is_focused_and_skips_only_installation() -> None:
    text, workflow = _workflow()
    contract = workflow["jobs"]["contract"]

    assert contract["name"] == "Public-release verifier contract"
    assert contract["runs-on"] == "ubuntu-24.04"
    assert any(step.get("uses") == SETUP_PYTHON_ACTION for step in contract["steps"])
    install = next(
        step
        for step in contract["steps"]
        if step.get("name") == "Install focused validation tooling"
    )
    assert install["run"] == 'python -m pip install --upgrade pip ".[dev]"'
    commands = {
        step["name"]: step["run"]
        for step in contract["steps"]
        if "name" in step and "run" in step
    }
    regressions = commands["Run post-release and compatibility regressions"]
    lint = commands["Lint post-release and compatibility contracts"]
    compile_contracts = commands["Compile post-release and compatibility contracts"]
    for historical_test in (
        "tests/test_public_release_verifier_2_2.py",
        "tests/test_post_release_workflow_2_2.py",
    ):
        assert historical_test in regressions
        assert historical_test in lint
        assert historical_test in compile_contracts
    assert "tools/verify_public_release_2_2.py" in lint
    assert "tools/verify_public_release_2_2.py" in compile_contracts
    for required in (
        "tests/test_public_release_verifier_2_2_1.py",
        "tests/test_public_release_verifier_2_2.py",
        "tests/test_post_release_workflow_2_2_1.py",
        "tests/test_post_release_workflow_2_2.py",
        "tests/test_required_workflows_2_2_1.py",
        "tests/test_release_workflows_2_2_1.py",
        "tools/verify_public_release_2_2.py",
        "tools/verify_2_2_release_readiness.py",
    ):
        assert required in text
    verifier_steps = [
        step
        for step in contract["steps"]
        if step.get("name") == "Verify exact immutable public state without reinstalling"
    ]
    assert len(verifier_steps) == 1
    assert verifier_steps[0]["run"] == (
        "python tools/verify_public_release_2_2_1.py --skip-install"
    )
    assert verifier_steps[0]["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}


def test_post_release_public_matrix_has_exact_three_install_cells() -> None:
    _, workflow = _workflow()
    public_install = workflow["jobs"]["public-install"]

    assert public_install["name"] == (
        "Public install ${{ matrix.os }} / CPython ${{ matrix.python-version }}"
    )
    assert public_install["needs"] == "contract"
    assert public_install["strategy"] == {
        "fail-fast": "false",
        "matrix": {
            "include": [
                {"os": "ubuntu-latest", "python-version": "3.13"},
                {"os": "macos-latest", "python-version": "3.13"},
                {"os": "windows-latest", "python-version": "3.14"},
            ]
        },
    }
    verifier = next(
        step
        for step in public_install["steps"]
        if step.get("name") == "Verify immutable public release and isolated installation"
    )
    assert verifier["run"] == "python tools/verify_public_release_2_2_1.py"
    assert "--skip-install" not in verifier["run"]
    assert verifier["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
