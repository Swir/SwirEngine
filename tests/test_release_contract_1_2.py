from pathlib import Path

from tools.verify_1_2_release_candidate import audit, parse_roadmap


ROOT = Path(__file__).resolve().parents[1]


def test_roadmap_parser_matches_active_1_2_dashboard() -> None:
    state = parse_roadmap((ROOT / "ROADMAP_1_2.md").read_text(encoding="utf-8"))

    assert state.total == 10
    assert state.completed in {9, 10}
    assert state.remaining == 10 - state.completed
    assert state.bar.endswith(f"{state.percent:.1f}%")
    assert len(state.bar.split()[0]) == 20


def test_development_release_contract_is_self_consistent() -> None:
    report = audit(ROOT)

    assert report.roadmap.total == 10
    assert report.version in {"1.1.0", "1.2.0"}
    assert len(report.checks) >= 40
