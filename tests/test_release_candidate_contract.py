from pathlib import Path

from tools.verify_1_1_release_candidate import audit, parse_roadmap

ROOT = Path(__file__).resolve().parents[1]


def test_release_candidate_contract_is_internally_consistent() -> None:
    report = audit(ROOT)

    assert report.version == "1.1.1"
    assert report.roadmap.total == 10
    assert report.roadmap.completed + report.roadmap.remaining == 10
    assert report.roadmap.percent == 100.0
    assert len(report.checks) >= 30


def test_complete_publication_gate_tracks_roadmap_state() -> None:
    report = audit(ROOT)

    if report.roadmap.completed == 10:
        complete = audit(ROOT, require_complete=True)
        assert complete.roadmap.percent == 100.0
    else:
        try:
            audit(ROOT, require_complete=True)
        except AssertionError as exc:
            assert "10/10" in str(exc)
        else:
            raise AssertionError("publication gate unexpectedly passed before roadmap completion")


def test_roadmap_parser_derives_twenty_segment_bar_from_checkboxes() -> None:
    text = "\n".join(["- [x] done"] * 7 + ["- [ ] todo"] * 3)
    state = parse_roadmap(text)

    assert state.completed == 7
    assert state.remaining == 3
    assert state.total == 10
    assert state.percent == 70.0
    assert state.bar == "██████████████░░░░░░ 70.0%"
