from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.generate_progress_svg import (
    ASCII_END,
    ASCII_START,
    CARD_PATH,
    MINI_PATH,
    STATUS_PATH,
    TEMPLATE_PATH,
    ProgressData,
    expected_outputs,
    generate,
    parse_progress,
    render_ascii_progress,
    render_card,
    render_mini,
    render_readme_with_ascii,
)

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
HISTORICAL_2_0_PATH = ROOT / "ROADMAP_2_0.md"
HISTORICAL_1_9_PATH = ROOT / "ROADMAP_1_9.md"
LEGACY_PROGRESS_RE = re.compile(
    r"(?:[█▓▒░]{2,}|\[(?=[^\]\n]*[#=█▓▒░])(?:[#=█▓▒░ .-]){6,}\])"
)
PYPI_ASCII_BLOCK_RE = re.compile(
    rf"{re.escape(ASCII_START)}.*?{re.escape(ASCII_END)}",
    re.DOTALL,
)


def _gradient_fill_width(svg: str) -> float | None:
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    for rect in root.findall("svg:rect", namespace):
        if rect.attrib.get("fill") == "url(#progressGradient)":
            return float(rect.attrib["width"])
    return None


def test_authoritative_post_release_math_matches_committed_assets() -> None:
    data = parse_progress(STATUS_PATH.read_text(encoding="utf-8"))

    assert STATUS_PATH.as_posix() == "docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md"
    assert data.total == 10
    assert data.percentage == pytest.approx(data.completed / data.total * 100.0)
    assert generate(check=True) == 0
    assert CARD_PATH.is_file()
    assert MINI_PATH.is_file()
    assert TEMPLATE_PATH.is_file()

    card = CARD_PATH.read_text(encoding="utf-8")
    mini = MINI_PATH.read_text(encoding="utf-8")
    assert _gradient_fill_width(card) == pytest.approx(1100.0 * data.completed / data.total)
    assert _gradient_fill_width(mini) == pytest.approx(700.0 * data.completed / data.total)
    assert data.display_percentage in card
    assert data.display_percentage in mini
    assert f"{data.completed} / {data.total}" in card
    assert f"{data.completed} / {data.total}" in mini


def test_pypi_ascii_progress_is_single_deterministic_exception() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    data = parse_progress(STATUS_PATH.read_text(encoding="utf-8"))

    assert readme.count(ASCII_START) == 1
    assert readme.count(ASCII_END) == 1
    match = PYPI_ASCII_BLOCK_RE.search(readme)
    assert match is not None
    assert match.group(0) == render_ascii_progress(data)
    assert render_readme_with_ascii(readme, data) == readme
    assert all(ord(character) < 128 for character in match.group(0))
    assert LEGACY_PROGRESS_RE.search(match.group(0)) is not None


def test_maintained_progress_surfaces_are_svg_only_and_nonduplicated() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    status = STATUS_PATH.read_text(encoding="utf-8")
    historical_2_0 = HISTORICAL_2_0_PATH.read_text(encoding="utf-8")
    historical_1_9 = HISTORICAL_1_9_PATH.read_text(encoding="utf-8")

    assert "<!-- SWIR-README-STANDARD:v2 -->" in readme

    readme_without_pypi_exception = PYPI_ASCII_BLOCK_RE.sub("", readme, count=1)
    for path, text in (
        (README_PATH, readme_without_pypi_exception),
        (STATUS_PATH, status),
        (HISTORICAL_2_0_PATH, historical_2_0),
        (HISTORICAL_1_9_PATH, historical_1_9),
    ):
        assert not LEGACY_PROGRESS_RE.search(text), f"legacy progress meter found in {path}"
        assert "progress-template.svg" not in text

    assert readme.count("assets/readme/progress-card.svg") == 1
    assert "assets/readme/progress-mini.svg" not in readme
    assert status.count("../assets/readme/progress-mini.svg") == 1
    assert "progress-card.svg" not in status
    assert "progress-mini.svg" not in historical_2_0
    assert "progress-mini.svg" not in historical_1_9


def test_template_is_valid_but_never_live_project_data() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data = parse_progress(STATUS_PATH.read_text(encoding="utf-8"))

    assert "TEMPLATE / NOT PROJECT DATA" in template
    assert data.scope not in template
    assert data.display_percentage not in template
    assert f"{data.completed} / {data.total}" not in template
    assert "Published 2.0.0" not in template
    assert ET.fromstring(template).tag.endswith("svg")


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
    data = ProgressData(completed, total, "fixture.md", scope="Fixture audit")

    assert _gradient_fill_width(render_card(data)) == expected_card
    assert _gradient_fill_width(render_mini(data)) == expected_mini


def test_unknown_denominator_renders_na_without_fake_progress() -> None:
    data = ProgressData(0, 0, "unknown.md", scope="Unknown scope")

    card = render_card(data)
    mini = render_mini(data)

    assert data.status == "N/A"
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
            "A deliberately long verified post-release audit scope that needs more than one visual line "
            "without overlapping the project status or progress geometry"
        ),
    )

    card = render_card(data)
    root = ET.fromstring(card)

    assert root.attrib["height"] == "210"
    assert root.attrib["viewBox"] == "0 0 1200 210"


def test_parse_progress_rejects_contradictory_summary() -> None:
    text = """
Current verified progress: 9/10 milestones = 90.0%.
- [x] **1. Done**
- [ ] **2. Pending**
""".strip()

    with pytest.raises(ValueError, match="disagrees"):
        parse_progress(text, source="bad.md")


def test_empty_scope_is_na_not_zero_or_complete() -> None:
    data = parse_progress("# Planning\nNo verified milestones yet.\n", source="planning.md")

    assert data.total == 0
    assert data.percentage is None
    assert data.status == "N/A"
    assert data.display_percentage == "N/A"


def test_all_generated_svgs_are_valid_xml() -> None:
    data = ProgressData(3, 10, "fixture.md")

    for content in expected_outputs(data).values():
        root = ET.fromstring(content)
        assert root.tag.endswith("svg")
