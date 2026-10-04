from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/post-release-2.2.yml"
CHECKOUT_ACTION = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON_ACTION = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
EXPECTED_SOURCE = "${{ github.event.pull_request.head.sha || github.sha }}"


def _workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return text, parsed


def test_post_release_workflow_has_exact_identity_triggers_and_permissions() -> None:
    text, workflow = _workflow()

    assert workflow["name"] == "Post-release 2.2 Public Verification"
    assert set(workflow["on"]) == {"pull_request", "push"}
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["pull_request"]["paths"] == workflow["on"]["push"]["paths"]
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert workflow["env"] == {"EXPECTED_SOURCE_SHA": EXPECTED_SOURCE}
    assert "workflow_dispatch" not in text
    for forbidden in (
        "contents: write",
        "id-token: write",
        "pypa/gh-action-pypi-publish",
        "twine upload",
        "gh release create",
        "git push",
    ):
        assert forbidden not in text


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
        assert any(
            "git rev-parse HEAD" in step.get("run", "") for step in job["steps"]
        )
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
    assert "tests/test_public_release_verifier_2_2.py" in text
    assert "tests/test_post_release_workflow_2_2.py" in text
    assert "tools/verify_2_2_release_readiness.py" in text
    verifier_steps = [
        step
        for step in contract["steps"]
        if step.get("name") == "Verify exact immutable public state without reinstalling"
    ]
    assert len(verifier_steps) == 1
    assert verifier_steps[0]["run"] == (
        "python tools/verify_public_release_2_2.py --skip-install"
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
    assert verifier["run"] == "python tools/verify_public_release_2_2.py"
    assert "--skip-install" not in verifier["run"]
    assert verifier["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
