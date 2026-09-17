from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = PROJECT_ROOT / "tools" / "verify_1_7_source_checkpoint.py"


def _load_auditor():
    spec = importlib.util.spec_from_file_location("verify_1_7_source_checkpoint", AUDITOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_milestone_progress_counts_only_numbered_top_level_milestones() -> None:
    auditor = _load_auditor()
    text = (
        "- [x] **1. Done**\n"
        "  - [ ] nested detail\n"
        "- [ ] **2. Pending**\n"
        "- [x] unrelated checkbox"
    )
    assert auditor.milestone_progress(text) == (1, 2)


def test_strict_checkpoint_matches_repository_contract() -> None:
    auditor = _load_auditor()
    checked, total = auditor.validate_checkpoint(PROJECT_ROOT, require_complete=True)
    assert (checked, total) == (10, 10)
    assert auditor.STABLE_PUBLIC_VERSION == "1.5.0"


def test_checkpoint_required_file_contract_has_no_duplicates() -> None:
    auditor = _load_auditor()
    required = auditor.REQUIRED_17_FILES + auditor.LOCKED_COMPATIBILITY_FILES
    assert len(required) == len(set(required))
    assert all((PROJECT_ROOT / relative).is_file() for relative in required)


def test_checkpoint_has_no_intermediate_publication_path() -> None:
    auditor = _load_auditor()
    assert all(not (PROJECT_ROOT / relative).exists() for relative in auditor.FORBIDDEN_17_PUBLICATION_FILES)
    workflow = (PROJECT_ROOT / ".github/workflows/source-checkpoint-1-7.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow
    assert "pypi" not in workflow.lower()
    assert "release:" not in workflow.lower()


def test_strict_checkpoint_refuses_incomplete_progress() -> None:
    auditor = _load_auditor()
    roadmap = "\n".join(f"- [{'x' if index < 9 else ' '}] **{index + 1}. Milestone**" for index in range(10))
    checked, total = auditor.milestone_progress(roadmap)
    assert (checked, total) == (9, 10)
    with pytest.raises(AssertionError, match="strict source checkpoint requires 10/10"):
        auditor._assert(
            checked == total == auditor.EXPECTED_MILESTONES,
            f"strict source checkpoint requires 10/10 milestones; found {checked}/{total}",
        )


@pytest.mark.parametrize("version", ["1.3", "1.4", "1.5", "1.6"])
def test_locked_prior_roadmaps_remain_complete(version: str) -> None:
    auditor = _load_auditor()
    auditor._assert_locked_roadmap(PROJECT_ROOT, version)
