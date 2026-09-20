from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.generate_progress_svg import (
    BAR_WIDTH,
    PROGRESS_END,
    PROGRESS_START,
    STATUS_PATH,
    TEMPLATE_PATH,
    ProgressData,
    build_readme_progress_block,
    build_roadmap_progress_block,
    generate,
    parse_progress,
    render_progress_line,
    render_text_meter,
)

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
GRAPHIC_PROGRESS_RE = re.compile(
    r"(?:progress-(?:card|mini|2-1-card|2-1-mini)\.svg|"
    r"!\[[^\]]*progress[^\]]*\]\([^)]*\)|"
    r"<img[^>]+(?:progress-card|progress-mini|progress-2-1)[^>]*>)",
    re.IGNORECASE,
)


def _block(text: str) -> str:
    assert text.count(PROGRESS_START) == 1
    assert text.count(PROGRESS_END) == 1
    start = text.index(PROGRESS_START)
    end = text.index(PROGRESS_END, start) + len(PROGRESS_END)
    return text[start:end]


def test_active_2_1_math_matches_canonical_text_progress() -> None:
    roadmap = (ROOT / STATUS_PATH).read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    data = parse_progress(roadmap)

    assert STATUS_PATH.as_posix() == "ROADMAP_2_1.md"
    assert data.total == 10
    assert data.percentage == pytest.approx((data.completed / data.total) * 100.0)
    assert len(render_text_meter(data).strip("[]")) == BAR_WIDTH
    assert _block(readme) == build_readme_progress_block(data)
    assert _block(roadmap) == build_roadmap_progress_block(data)
    assert generate(check=True) == 0


def test_active_progress_surfaces_are_text_only_and_nonduplicated() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    roadmap = (ROOT / STATUS_PATH).read_text(encoding="utf-8")
    data = parse_progress(roadmap)
    meter = render_text_meter(data)

    assert "<!-- SWIR-README-STANDARD:v2 -->" in readme
    assert roadmap.startswith("<!-- SWIR-PROGRESS-TEXT:v1 -->")
    assert not GRAPHIC_PROGRESS_RE.search(readme)
    assert not GRAPHIC_PROGRESS_RE.search(roadmap)
    assert "<!-- SWIR-PYPI-PROGRESS:START -->" not in readme
    assert "<!-- SWIR-PYPI-PROGRESS:END -->" not in readme
    assert not re.search(r"[█▓▒░]{2,}", readme)
    assert not re.search(r"[█▓▒░]{2,}", roadmap)
    assert _block(readme).count(meter) == 1
    assert _block(roadmap).count(meter) == 1
    assert render_progress_line(data).endswith(f"(**{data.completed}/{data.total} milestones**)")


def test_template_remains_valid_labelled_internal_asset() -> None:
    template = (ROOT / TEMPLATE_PATH).read_text(encoding="utf-8")
    active = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))

    assert "TEMPLATE / NOT PROJECT DATA" in template
    assert active.scope not in template
    assert active.display_percentage not in template
    assert ET.fromstring(template).tag.endswith("svg")


@pytest.mark.parametrize(
    ("completed", "total", "expected"),
    [
        (0, 10, "[----------]"),
        (1, 4, "[###-------]"),
        (3, 10, "[###-------]"),
        (6, 10, "[######----]"),
        (4, 4, "[##########]"),
    ],
)
def test_text_progress_meter_is_bounded_and_deterministic(
    completed: int,
    total: int,
    expected: str,
) -> None:
    data = ProgressData(completed, total, "fixture.md", scope="Fixture roadmap")
    assert render_text_meter(data) == expected


def test_unknown_denominator_is_na_without_fake_meter() -> None:
    data = ProgressData(0, 0, "unknown.md", scope="Unknown scope")

    assert data.status == "N/A"
    assert data.display_percentage == "N/A"
    assert render_text_meter(data) == "N/A"
    assert render_progress_line(data) == "**Progress:** N/A (**N/A milestones**)"


def test_parse_progress_rejects_duplicate_or_out_of_order_milestones() -> None:
    duplicate = "- [x] **1. Done**\n- [ ] **1. Duplicate**\n"
    out_of_order = "- [x] **2. Later**\n- [ ] **1. Earlier**\n"

    with pytest.raises(ValueError, match="unique"):
        parse_progress(duplicate, source="duplicate.md")
    with pytest.raises(ValueError, match="ordered"):
        parse_progress(out_of_order, source="order.md")


def test_empty_scope_is_na_not_zero_or_complete() -> None:
    data = parse_progress("# Planning\nNo verified milestones yet.\n", source="planning.md")

    assert data.total == 0
    assert data.percentage is None
    assert data.status == "N/A"
    assert data.display_percentage == "N/A"
