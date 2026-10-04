from __future__ import annotations

import re
from pathlib import Path

import yaml

from tools.verify_2_2_1_release_candidate import validate_candidate_workflow
from tools.verify_required_workflows_2_2 import load_manifest, verify_manifest_files

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / ".github/workflows/release-candidate-2.2.1.yml"
PUBLICATION_GATE = ROOT / ".github/workflows/publication-gate-2.2.1.yml"
MANIFEST = ROOT / ".github/release-gates/2.2.1-required-workflows.json"


def _yaml(path: Path) -> tuple[str, dict[str, object]]:
    text = path.read_text(encoding="utf-8")
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


def test_actual_candidate_workflow_is_non_publishing_and_exact_source() -> None:
    text, workflow = _yaml(CANDIDATE)

    assert validate_candidate_workflow(text) == []
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["env"] == {
        "EXPECTED_SOURCE_SHA": "${{ github.event.pull_request.head.sha }}"
    }
    for test_path in (
        "tests/test_verify_2_2_1_release_candidate.py",
        "tests/test_candidate_evidence_2_2_1.py",
        "tests/test_reconcile_release_2_2_1.py",
        "tests/test_release_tools_2_2_1.py",
        "tests/test_required_workflows_2_2_1.py",
        "tests/test_release_workflows_2_2_1.py",
    ):
        assert test_path in text
    _assert_actions_are_commit_pinned(workflow)


def test_actual_publication_gate_is_read_only_marker_push_only() -> None:
    text, workflow = _yaml(PUBLICATION_GATE)

    assert workflow["name"] == "SwirEngine 2.2.1 Publication Gate"
    assert workflow["on"] == {
        "push": {
            "branches": ["release/2.2.1-publication"],
            "paths": [".release/publish-2.2.1/publication.json"],
        }
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert "contents: write" not in text
    assert "id-token: write" not in text
    assert "tools/verify_publication_chain_2_2_1.py" in text
    assert 'python "$candidate_root/tools/verify_2_2_1_release_candidate.py"' in text
    assert 'git worktree add --detach "$candidate_root" "$CANDIDATE_SOURCE_SHA"' in text
    _assert_actions_are_commit_pinned(workflow)


def test_patch_manifest_resolves_all_48_exact_workflow_names() -> None:
    manifest = load_manifest(MANIFEST)

    verified = verify_manifest_files(manifest, ROOT)

    assert len(verified) == 48
