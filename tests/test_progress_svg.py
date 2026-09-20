from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.generate_progress_svg import (
    README_END,
    README_START,
    ROADMAP_END,
    ROADMAP_START,
    STATUS_PATH,
    ProgressData,
    expected_outputs,
    generate,
    parse_progress,
    render_ascii,
    render_pypi_progress,
)

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"


def test_active_2_1_math_matches_ascii_presentation() -> None:
    data = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))
    assert data.total == 10
    assert data.percentage == pytest.approx((data.completed / data.total) * 100.0)
    assert generate(check=True) == 0
    assert expected_outputs(data) == {}


def test_readme_has_single_deterministic_ascii_progress_block() -> None:
    data = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))
    readme = README_PATH.read_text(encoding="utf-8")
    assert readme.count(README_START) == 1
    assert readme.count(README_END) == 1
    assert render_pypi_progress(data) in readme
    assert "assets/readme/progress-card.svg" not in readme
    assert "assets/readme/progress-mini.svg" not in readme


def test_roadmap_has_single_ascii_progress_block_and_no_graphical_meter() -> None:
    roadmap = (ROOT / STATUS_PATH).read_text(encoding="utf-8")
    assert roadmap.count(ROADMAP_START) == 1
    assert roadmap.count(ROADMAP_END) == 1
    assert "assets/readme/progress-card.svg" not in roadmap
    assert "assets/readme/progress-mini.svg" not in roadmap
    assert "<!-- SWIR-PROGRESS-SVG-PRO:v1 -->" not in roadmap


@pytest.mark.parametrize(
    ("completed", "total", "expected"),
    [
        (0, 4, "[--------------------] 0.0%"),
        (1, 4, "[#####---------------] 25.0%"),
        (4, 4, "[####################] 100.0%"),
    ],
)
def test_ascii_progress_is_bounded(completed: int, total: int, expected: str) -> None:
    data = ProgressData(completed, total, "fixture.md", scope="Fixture roadmap")
    assert expected in render_ascii(data)


def test_unknown_denominator_renders_na_without_fake_bar() -> None:
    data = ProgressData(0, 0, "unknown.md", scope="Unknown scope")
    block = render_ascii(data)
    assert "Progress: N/A" in block
    assert "[#" not in block


def test_parse_progress_rejects_contradictory_summary() -> None:
    text = """
Current verified progress: 9/10 milestones = 90.0%.
- [x] **1. Done**
- [ ] **2. Pending**
""".strip()
    with pytest.raises(ValueError, match="disagrees"):
        parse_progress(text, source="bad.md")


def test_ascii_block_contains_only_simple_text_meter_symbols() -> None:
    data = ProgressData(5, 10)
    block = render_ascii(data)
    meter = re.search(r"\[[#-]{20}\]\s+50\.0%", block)
    assert meter is not None
    assert not re.search(r"[█▓▒░]", block)
