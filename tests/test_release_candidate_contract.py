from pathlib import Path

from tools.verify_1_2_release_candidate import parse_roadmap

ROOT = Path(__file__).resolve().parents[1]


def test_published_1_2_roadmap_remains_locked_and_complete() -> None:
    roadmap_text = (ROOT / "ROADMAP_1_2.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap_text)

    assert state.completed == 10
    assert state.remaining == 0
    assert state.total == 10
    assert state.percent == 100.0
    assert state.bar == "████████████████████ 100.0%"
    assert "STATUS-COMPLETE" in roadmap_text


def test_historical_1_2_release_artifacts_remain_documented() -> None:
    release_note = (ROOT / "CHANGELOG.d/1.2.0-creator-hardening.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP_1_2.md").read_text(encoding="utf-8")

    assert "## 1.2.0" in release_note
    assert "SwirEngine 1.2.0 completes" in release_note
    assert "SwirEngine 1.2" in roadmap
    assert (ROOT / "tools/verify_1_2_release_candidate.py").is_file()


def test_active_release_workflow_uses_final_2_1_gate_and_keeps_historical_gates_separate() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    historical = (ROOT / ".github/workflows/release-2.0.yml").read_text(encoding="utf-8")

    assert "verify_1_3_release_candidate.py" in ci
    assert "verify_2_1_publication.py" in release
    assert "verify_2_1_release_readiness.py" in release
    assert "verify_2_0_release_candidate.py --require-final" in historical
    assert "verify_1_3_release_candidate.py --require-complete" not in release
    assert "verify_1_2_release_candidate.py --require-complete" not in release


def test_roadmap_parser_derives_twenty_segment_bar_from_checkboxes() -> None:
    text = "\n".join(["- [x] done"] * 7 + ["- [ ] todo"] * 3)
    state = parse_roadmap(text)

    assert state.completed == 7
    assert state.remaining == 3
    assert state.total == 10
    assert state.percent == 70.0
    assert state.bar == "██████████████░░░░░░ 70.0%"
