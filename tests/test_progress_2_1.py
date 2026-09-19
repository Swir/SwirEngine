from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.generate_2_1_progress_svg import (
    CARD_PATH,
    MINI_PATH,
    STATUS_PATH,
    expected_outputs,
    parse_progress,
)

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROGRESS_RE = re.compile(
    r"(?:[█▓▒░]{2,}|\[(?=[^\]\n]*[#=█▓▒░])(?:[#=█▓▒░ .-]){6,}\])"
)


def test_2_1_roadmap_math_matches_generated_assets() -> None:
    data = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))
    assert data.completed == 3
    assert data.total == 10
    assert data.display_percentage == "30.0%"
    assert data.status == "IN PROGRESS"

    outputs = expected_outputs(data)
    assert (ROOT / CARD_PATH).read_text(encoding="utf-8") == outputs[CARD_PATH]
    assert (ROOT / MINI_PATH).read_text(encoding="utf-8") == outputs[MINI_PATH]


def test_2_1_progress_svgs_are_valid_accessible_and_have_verified_fill() -> None:
    data = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))
    outputs = expected_outputs(data)
    for svg in outputs.values():
        root = ET.fromstring(svg)
        assert root.attrib["viewBox"]
        assert root.find("{http://www.w3.org/2000/svg}title") is not None
        assert root.find("{http://www.w3.org/2000/svg}desc") is not None
        assert "30.0%" in svg
        assert "3 / 10 milestones" in svg

    card = outputs[CARD_PATH]
    mini = outputs[MINI_PATH]
    assert 'width="330.000000" height="18"' in card
    assert 'filter="url(#softGlow)" clip-path="url(#trackClip)"' in card
    assert 'width="210.000000" height="10"' in mini


def test_2_1_roadmap_has_no_legacy_character_progress_meter() -> None:
    roadmap = (ROOT / STATUS_PATH).read_text(encoding="utf-8")
    assert LEGACY_PROGRESS_RE.search(roadmap) is None
