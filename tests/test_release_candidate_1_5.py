from __future__ import annotations

from pathlib import Path

import pytest

from tools.verify_1_5_release_candidate import audit, parse_roadmap


ROOT = Path(__file__).resolve().parents[1]


def test_release_contract_audits_current_hardening_state() -> None:
    report = audit(ROOT)
    assert report.roadmap.total == 10
    assert report.roadmap.completed in {9, 10}
    assert report.version in {"1.4.0", "1.5.0"}
    assert report.checks


def test_strict_release_contract_tracks_roadmap_completion() -> None:
    report = audit(ROOT)
    if report.roadmap.completed == 10:
        strict = audit(ROOT, require_complete=True)
        assert strict.version == "1.5.0"
        assert strict.roadmap.remaining == 0
    else:
        with pytest.raises(AssertionError, match="10/10"):
            audit(ROOT, require_complete=True)


def test_parse_roadmap_derives_progress_from_checkboxes() -> None:
    state = parse_roadmap("- [x] one\n- [x] two\n- [ ] three\n- [ ] four\n")
    assert state.completed == 2
    assert state.remaining == 2
    assert state.total == 4
    assert state.percent == 50.0
    assert state.bar == "██████████░░░░░░░░░░ 50.0% — 2/4"
