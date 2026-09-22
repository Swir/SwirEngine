from __future__ import annotations

from pathlib import Path

import pytest

from tools.verify_2_1_release_readiness import (
    PYPI_BLOCK_RE,
    audit,
    expected_pypi_progress,
    parse_roadmap,
    require_preflight_roadmap,
    validate_pypi_progress,
)

ROOT = Path(__file__).resolve().parents[1]


def test_repository_passes_2_1_release_readiness_preflight() -> None:
    report = audit(ROOT)

    assert report.version == "2.0.0"
    assert report.roadmap.completed == 9
    assert report.roadmap.total == 10
    assert report.roadmap.percent == pytest.approx(90.0)


def test_preflight_rejects_closing_m10_before_final_acceptance() -> None:
    roadmap = (ROOT / "ROADMAP_2_1.md").read_text(encoding="utf-8")
    completed = roadmap.replace(
        "- [ ] **10. Real-game editor gate and 2.1 release readiness.**",
        "- [x] **10. Real-game editor gate and 2.1 release readiness.**",
        1,
    ).replace(
        "Current verified progress: 9/10 milestones = 90.0%.",
        "Current verified progress: 10/10 milestones = 100.0%.",
        1,
    )
    state = parse_roadmap(completed)

    with pytest.raises(AssertionError, match="must remain at 9/10"):
        require_preflight_roadmap(completed, state)


def test_preflight_rejects_svg_inside_pypi_progress_block() -> None:
    roadmap = (ROOT / "ROADMAP_2_1.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    expected = expected_pypi_progress(state)
    graphical = (
        "<!-- SWIR-PYPI-PROGRESS:START -->\n"
        '<img src="assets/readme/progress-card.svg" alt="progress" />\n'
        "<!-- SWIR-PYPI-PROGRESS:END -->"
    )
    broken = readme.replace(expected, graphical, 1)

    with pytest.raises(AssertionError, match="must exactly match"):
        validate_pypi_progress(broken, state)


def test_preflight_rejects_ascii_counter_drift() -> None:
    roadmap = (ROOT / "ROADMAP_2_1.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = PYPI_BLOCK_RE.search(readme)
    assert match is not None
    broken_block = match.group(0).replace(
        "Counter: 9 / 10 milestones",
        "Counter: 8 / 10 milestones",
        1,
    )
    broken = readme[: match.start()] + broken_block + readme[match.end() :]

    with pytest.raises(AssertionError, match="must exactly match"):
        validate_pypi_progress(broken, state)
