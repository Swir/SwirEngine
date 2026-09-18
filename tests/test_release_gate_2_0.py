from pathlib import Path

from tools.verify_2_0_release_candidate import audit, legacy_progress_meter_lines, parse_roadmap

ROOT = Path(__file__).resolve().parents[1]


def test_release_candidate_preflight_contract_matches_current_repository():
    report = audit(ROOT)
    assert report.version == "1.5.0"
    assert report.roadmap.completed == 9
    assert report.roadmap.remaining == 1
    assert report.roadmap.total == 10
    assert report.roadmap.percent == 90.0
    assert len(report.checks) >= 40


def test_roadmap_parser_counts_only_top_level_milestones():
    state = parse_roadmap(
        "\n".join(
            (
                "- [x] one",
                "  - [x] nested evidence",
                "- [ ] two",
                "- [X] three",
            )
        )
    )
    assert state.completed == 2
    assert state.remaining == 1
    assert state.total == 3
    assert state.percent == 200 / 3


def test_legacy_progress_meter_detection_blocks_character_bars_only():
    assert legacy_progress_meter_lines("status █████░░░░░ 50%")
    assert legacy_progress_meter_lines("[#####-----] 50%")
    assert legacy_progress_meter_lines("■■■■■□□□□□")
    assert legacy_progress_meter_lines("plain 9/10 = 90.0%") == ()
    assert legacy_progress_meter_lines("python -m compileall -q src tests") == ()
    assert legacy_progress_meter_lines("assets/readme/progress-mini.svg") == ()
