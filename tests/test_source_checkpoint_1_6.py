from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = PROJECT_ROOT / "tools" / "verify_1_6_source_checkpoint.py"


def _load_auditor():
    spec = importlib.util.spec_from_file_location("verify_1_6_source_checkpoint", AUDITOR_PATH)
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


def test_development_checkpoint_matches_repository_contract() -> None:
    auditor = _load_auditor()
    checked, total = auditor.validate_checkpoint(PROJECT_ROOT, require_complete=False)
    assert total == 10
    assert 0 <= checked <= total
    assert auditor.STABLE_PUBLIC_VERSION == "1.5.0"


def test_strict_checkpoint_refuses_an_incomplete_roadmap(tmp_path: Path) -> None:
    auditor = _load_auditor()
    roadmap = "\n".join(f"- [{'x' if index < 9 else ' '}] **{index + 1}. Milestone**" for index in range(10))
    assert auditor.milestone_progress(roadmap) == (9, 10)
    with pytest.raises(AssertionError, match="strict source checkpoint requires 10/10"):
        checked, total = auditor.milestone_progress(roadmap)
        auditor._assert(checked == total == 10, f"strict source checkpoint requires 10/10 milestones; found {checked}/{total}")
