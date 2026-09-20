from __future__ import annotations

from pathlib import Path

from tools import generate_2_1_progress_svg as compatibility
from tools import generate_progress_svg as canonical

ROOT = Path(__file__).resolve().parents[1]


def test_2_1_compatibility_generator_delegates_to_canonical_active_generator() -> None:
    assert compatibility.STATUS_PATH == canonical.STATUS_PATH
    assert compatibility.TEMPLATE_PATH == canonical.TEMPLATE_PATH
    assert compatibility.BAR_WIDTH == canonical.BAR_WIDTH
    assert compatibility.PROGRESS_START == canonical.PROGRESS_START
    assert compatibility.PROGRESS_END == canonical.PROGRESS_END

    data = compatibility.parse_progress((ROOT / compatibility.STATUS_PATH).read_text(encoding="utf-8"))
    assert data.total == 10
    assert 0 <= data.completed <= data.total
    assert data.percentage == (data.completed / data.total) * 100.0
    assert data.display_percentage == f"{data.percentage:.1f}%"
    assert compatibility.render_text_meter(data) == canonical.render_text_meter(data)
    assert compatibility.render_progress_line(data) == canonical.render_progress_line(data)
