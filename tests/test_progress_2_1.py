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
    assert data.completed == 0
    assert data.total == 10
    assert data.display_percentage == "0.0%"
    assert data.status == "IN PROGRESS"

    outputs = expected_outputs(data)
    assert (ROOT / CARD_PATH).read_text(encoding="utf-8") == outputs[CARD_PATH]
    assert (ROOT / MINI_PATH).read_text(encoding="utf-8") == outputs[MINI_PATH]


def test_2_1_progress_svgs_are_valid_accessible_and_zero_fill_is_not_glowing() -> None:
    data = parse_progress((ROOT / STATUS_PATH).read_text(encoding="utf-8"))
    for relative, svg in expected_outputs(data).items():
        root = ET.fromstring(svg)
        assert root.attrib["viewBox"]
        assert root.find("{http://www.w3.org/2000/svg}title") is not None
        assert root.find("{http://www.w3.org/2000/svg}desc") is not None
        assert "0.0%" in svg
        assert "0 / 10 milestones" in svg
        if relative == CARD_PATH:
            assert 'filter="url(#softGlow)" clip-path="url(#trackClip)"' not in svg


def test_2_1_roadmap_has_no_legacy_character_progress_meter() -> None:
    roadmap = (ROOT / STATUS_PATH).read_text(encoding="utf-8")
    assert LEGACY_PROGRESS_RE.search(roadmap) is None
