from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path

import yaml

from tools.verify_required_workflows_2_2 import load_manifest, verify_manifest_files

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / ".github/release-gates/2.2-required-workflows.json"
NEW = ROOT / ".github/release-gates/2.2.1-required-workflows.json"
CANDIDATE = ROOT / ".github/workflows/release-candidate-2.2.1.yml"
CANDIDATE_FIXTURE = ROOT / "tests/fixtures/release-candidate-2.2.1.yml"
CANDIDATE_WORKFLOW_ENTRY = {
    "path": ".github/workflows/release-candidate-2.2.1.yml",
    "name": "SwirEngine 2.2.1 Release Candidate",
}
POST_RELEASE_WORKFLOW_ENTRY = {
    "path": ".github/workflows/post-release-2.2.1.yml",
    "name": "Post-release 2.2.1 Public Verification",
}
PHASE_E_PLANNED_FILES = (
    ".gitattributes",
    ".github/release-gates/2.2.1-required-workflows.json",
    ".github/workflows/post-release-2.2.1.yml",
    ".github/workflows/release-candidate-2.2.1.yml",
    "CHANGELOG.md",
    "README.md",
    "ROADMAP_2_2.md",
    "assets/readme/progress-2-2-card.svg",
    "assets/readme/progress-2-2-mini.svg",
    "assets/readme/progress-card.svg",
    "assets/readme/progress-mini.svg",
    "docs/MIGRATING_TO_2_2.md",
    "docs/RELEASE_GATE_2_2.md",
    "release-evidence/2.2.1/manifest.json",
    "tests/fixtures/release-candidate-2.2.1.yml",
    "tests/test_post_release_workflow_2_2_1.py",
    "tests/test_public_release_verifier_2_2_1.py",
    "tests/test_required_workflows_2_2_1.py",
    "tests/test_release_workflows_2_2_1.py",
    "tools/generate_progress_svg.py",
    "tools/verify_2_2_release_readiness.py",
    "tools/verify_public_release_2_2_1.py",
)


def test_phase_e_manifest_replaces_only_the_appended_candidate_gate() -> None:
    assert hashlib.sha256(OLD.read_bytes()).hexdigest() == (
        "4b765c20736147881e99bc2a9414265815fbda2013bd20fc32d27be6f189e17a"
    )
    old = json.loads(OLD.read_text(encoding="utf-8"))
    new = json.loads(NEW.read_text(encoding="utf-8"))

    assert new["schema_version"] == old["schema_version"] == 1
    assert new["repository"] == old["repository"] == "Swir/SwirEngine"
    assert len(old["required_workflows"]) == 47
    assert len(new["required_workflows"]) == 48
    assert new["required_workflows"][:-1] == old["required_workflows"]
    assert new["required_workflows"][-1] == POST_RELEASE_WORKFLOW_ENTRY
    assert CANDIDATE_WORKFLOW_ENTRY not in new["required_workflows"]


def test_candidate_workflow_is_retired_to_a_historical_fixture() -> None:
    assert not CANDIDATE.exists()
    assert CANDIDATE_FIXTURE.is_file()
    assert CANDIDATE_FIXTURE.read_text(encoding="utf-8").startswith(
        "# Historical SwirEngine 2.2.1 Phase B workflow fixture. "
        "It is intentionally inactive.\n"
    )


def test_phase_e_manifest_resolves_all_48_exact_workflow_names() -> None:
    manifest = load_manifest(NEW)

    verified = verify_manifest_files(manifest, ROOT)

    assert len(verified) == 48


def test_all_48_required_workflows_are_triggered_by_the_phase_e_change_set() -> None:
    manifest = load_manifest(NEW)

    for required in manifest.workflows:
        workflow = yaml.load(
            (ROOT / required.path).read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        assert isinstance(workflow, dict)
        pull_request = workflow["on"]["pull_request"]
        if not isinstance(pull_request, dict) or "paths" not in pull_request:
            continue
        patterns = pull_request["paths"]
        assert any(
            any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)
            for relative in PHASE_E_PLANNED_FILES
        ), f"Phase E change set does not trigger {required.path}"
