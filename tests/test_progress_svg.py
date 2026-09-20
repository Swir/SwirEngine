from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.generate_progress_svg import (
    CARD_PATH,
    COMPAT_CARD_PATH,
    COMPAT_MINI_PATH,
    MINI_PATH,
    PYPI_BLOCK_RE,
    PYPI_PROGRESS_END,
    PYPI_PROGRESS_START,
    STATUS_PATH,
    TEMPLATE_PATH,
    ProgressData,
    expected_outputs,
    generate,
    parse_progress,
    render_card,
    render_mini,
    render_pypi_progress,
)

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
ARCHIVED_2_0_AUDIT_PATH = ROOT / "docs" / "SWIRENGINE_2_0_POST_RELEASE_AUDIT.md"
HISTORICAL_2_0_PATH = ROOT / "ROADMAP_2_0.md"
HISTORICAL_1_9_PATH = ROOT / "ROADMAP_1_9.md"
LEGACY_PROGRESS_RE = re.compile(
    r"(?:[█▓▒░]{2,}|\[(?=[^\]\n]*[#=█▓▒░])(?:[#=█▓▒░ .-]){6,}\])"
)


def _gradient_fill_width(svg: str) -> float | None:
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    for rect in root.findall("svg:rect", namespace):
        if rect.attrib.get("fill") == "url(#progressGradient)":
            return float(rect.attrib["width"])
    return None


def _without_approved_pypi_progress(text: str) -> str:
    return PYPI_BLOCK_RE.sub("", text)


def test_active_2_1_math_matches_canonical_assets() -> None:
    data = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))

    assert STATUS_PATH.as_posix() == "ROADMAP_2_1.md"
    assert data.total == 10
    assert data.percentage == pytest.approx((data.completed / data.total) * 100.0)
    assert generate(check=True) == 0

    outputs = expected_outputs(data)
    for path, expected in outputs.items():
        assert (ROOT / path).read_text(encoding="utf-8") == expected

    card = outputs[CARD_PATH]
    mini = outputs[MINI_PATH]
    assert _gradient_fill_width(card) == pytest.approx(1100.0 * data.completed / data.total)
    assert _gradient_fill_width(mini) == pytest.approx(700.0 * data.completed / data.total)
    assert "SwirEngine 2.1 — SwirEditor &amp; Creator Workflow" in card
    assert data.counter in card
    assert data.display_percentage in card
    assert outputs[COMPAT_CARD_PATH] == card
    assert outputs[COMPAT_MINI_PATH] == mini


def test_readme_pypi_fallback_is_single_deterministic_exception() -> None:
    data = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))
    readme = README_PATH.read_text(encoding="utf-8")

    assert readme.count(PYPI_PROGRESS_START) == 1
    assert readme.count(PYPI_PROGRESS_END) == 1
    match = PYPI_BLOCK_RE.search(readme)
    assert match is not None
    block = match.group(0)
    assert block == render_pypi_progress(data)
    assert block.startswith(f"{PYPI_PROGRESS_START}\n```text\n")
    assert block.endswith(f"\n```\n{PYPI_PROGRESS_END}")
    assert data.display_percentage in block
    assert data.counter in block
    assert not re.search(r"[█▓▒░]", block)


def test_maintained_progress_surfaces_are_svg_only_nonduplicated_and_scoped() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    roadmap = (ROOT / STATUS_PATH).read_text(encoding="utf-8")
    archived_audit = ARCHIVED_2_0_AUDIT_PATH.read_text(encoding="utf-8")
    historical_2_0 = HISTORICAL_2_0_PATH.read_text(encoding="utf-8")
    historical_1_9 = HISTORICAL_1_9_PATH.read_text(encoding="utf-8")

    assert "<!-- SWIR-README-STANDARD:v2 -->" in readme
    assert roadmap.startswith("<!-- SWIR-PROGRESS-SVG-PRO:v1 -->")

    for path, text in (
        (README_PATH, _without_approved_pypi_progress(readme)),
        (ROOT / STATUS_PATH, roadmap),
        (ARCHIVED_2_0_AUDIT_PATH, archived_audit),
        (HISTORICAL_2_0_PATH, historical_2_0),
        (HISTORICAL_1_9_PATH, historical_1_9),
    ):
        assert not LEGACY_PROGRESS_RE.search(text), f"legacy progress meter found in {path}"
        assert 'src="assets/readme/progress-template.svg"' not in text
        assert 'src="../assets/readme/progress-template.svg"' not in text

    assert readme.count("assets/readme/progress-card.svg") == 1
    assert 'src="assets/readme/progress-mini.svg"' not in readme
    assert roadmap.count("assets/readme/progress-mini.svg") == 1
    assert "progress-card.svg" not in roadmap
    assert "progress-2-0-audit-mini.svg" not in archived_audit
    assert "progress-mini.svg" not in archived_audit
    assert "progress-mini.svg" not in historical_2_0
    assert "progress-mini.svg" not in historical_1_9
    assert "2.0%20AUDIT" not in readme


def test_template_is_valid_labelled_and_never_live_project_data() -> None:
    template = (ROOT / TEMPLATE_PATH).read_text(encoding="utf-8")
    active = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))

    assert "TEMPLATE / NOT PROJECT DATA" in template
    assert active.scope not in template
    assert active.display_percentage not in template
    assert f"{active.completed} / {active.total}" not in template
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
    data = ProgressData(completed, total, "fixture.md", scope="Fixture roadmap")

    assert _gradient_fill_width(render_card(data)) == expected_card
    assert _gradient_fill_width(render_mini(data)) == expected_mini


def test_unknown_denominator_renders_na_without_fake_progress() -> None:
    data = ProgressData(0, 0, "unknown.md", scope="Unknown scope")
    card = render_card(data)
    mini = render_mini(data)
    pypi = render_pypi_progress(data)

    assert data.status == "N/A"
    assert "N/A" in card
    assert "N/A" in mini
    assert "Progress: N/A" in pypi
    assert "[" not in pypi
    assert _gradient_fill_width(card) is None
    assert _gradient_fill_width(mini) is None


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
