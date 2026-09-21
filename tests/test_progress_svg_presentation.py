from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ROADMAP = ROOT / "ROADMAP_2_1.md"
TEMPLATE = ROOT / "assets/readme/progress-template.svg"
README_CARD = "assets/readme/progress-card.svg"
ROADMAP_MINI = "assets/readme/progress-mini.svg"
TEMPLATE_REF = "assets/readme/progress-template.svg"
LEGACY_METER_RE = re.compile(
    r"(?m)^[ \t]*(?:```(?:text)?[ \t]*\n)?"
    r"[ \t]*\[[#=\-█▓▒░■□▰▱▮▯▉▊▋▌▍▎▏]{5,}\]"
    r"[ \t]+\d+(?:\.\d+)?%[ \t]*(?:\n```)?[ \t]*$"
)


def test_active_progress_surfaces_are_svg_only() -> None:
    readme = README.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")

    assert readme.count(README_CARD) == 1
    assert ROADMAP_MINI not in readme
    assert roadmap.count(ROADMAP_MINI) == 1
    assert README_CARD not in roadmap
    assert "SWIR-PYPI-PROGRESS" not in readme
    assert "SWIR-PYPI-PROGRESS" not in roadmap
    assert LEGACY_METER_RE.search(readme) is None
    assert LEGACY_METER_RE.search(roadmap) is None


def test_progress_template_is_labelled_and_never_embedded_as_live_data() -> None:
    readme = README.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")

    assert "TEMPLATE / NOT PROJECT DATA" in template
    assert TEMPLATE_REF not in readme
    assert TEMPLATE_REF not in roadmap
