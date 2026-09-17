from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from tools.generate_progress_svg import (
    CARD_PATH,
    MINI_PATH,
    ROADMAP_PATH,
    TEMPLATE_PATH,
    ProgressData,
    expected_outputs,
    generate,
    parse_progress,
    render_card,
    render_mini,
)


def _gradient_fill_width(svg: str) -> float | None:
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    for rect in root.findall("svg:rect", namespace):
        if rect.attrib.get("fill") == "url(#progressGradient)":
            return float(rect.attrib["width"])
    return None


def test_authoritative_roadmap_math_matches_committed_assets() -> None:
    data = parse_progress(ROADMAP_PATH.read_text(encoding="utf-8"))

    assert data.total > 0
    assert 0 <= data.completed <= data.total
    assert data.percentage == pytest.approx(data.completed / data.total * 100.0)
    assert generate(check=True) == 0
    assert CARD_PATH.is_file()
    assert MINI_PATH.is_file()
    assert TEMPLATE_PATH.is_file()


@pytest.mark.parametrize(
    ("completed", "total", "expected_card", "expected_mini"),
    [
        (0, 4, None, None),
        (1, 4, 275.0, 175.0),
        (4, 4, 1100.0, 700.0),
    ],
)
def test_progress_geometry_is_bounded(
    completed: int,
    total: int,
    expected_card: float | None,
    expected_mini: float | None,
) -> None:
    data = ProgressData(completed, total, "fixture.md", scope="Fixture roadmap")

    assert _gradient_fill_width(render_card(data)) == expected_card
    assert _gradient_fill_width(render_mini(data)) == expected_mini


def test_unknown_denominator_renders_na_without_fake_progress() -> None:
    data = ProgressData(0, 0, "unknown.md", scope="Unknown scope")

    card = render_card(data)
    mini = render_mini(data)

    assert "N/A" in card
    assert "N/A" in mini
    assert _gradient_fill_width(card) is None
    assert _gradient_fill_width(mini) is None


def test_long_scope_expands_card_height() -> None:
    data = ProgressData(
        1,
        10,
        "fixture.md",
        scope=(
            "A deliberately long verified roadmap scope that needs more than one visual line "
            "without overlapping the project status or progress geometry"
        ),
    )

    card = render_card(data)
    root = ET.fromstring(card)

    assert root.attrib["height"] == "210"
    assert root.attrib["viewBox"] == "0 0 1200 210"


def test_parse_progress_rejects_contradictory_summary() -> None:
    text = """
**Current verified progress: 9/10 milestones = 90.0%.**
- [x] **1. Done**
- [ ] **2. Pending**
""".strip()

    with pytest.raises(ValueError, match="disagrees"):
        parse_progress(text, source="bad.md")


def test_empty_scope_is_na_not_zero_or_complete() -> None:
    data = parse_progress("# Planning\nNo verified milestones yet.\n", source="planning.md")

    assert data.total == 0
    assert data.percentage is None
    assert data.status == "PLANNING"
    assert data.display_percentage == "N/A"


def test_all_generated_svgs_are_valid_xml() -> None:
    data = ProgressData(3, 10, "fixture.md")

    for content in expected_outputs(data).values():
        root = ET.fromstring(content)
        assert root.tag.endswith("svg")
        assert "viewBox" in root.attrib
