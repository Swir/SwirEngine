from __future__ import annotations

from pathlib import Path

from tools import generate_2_1_progress_svg as compatibility
from tools import generate_progress_svg as canonical

ROOT = Path(__file__).resolve().parents[1]


def test_2_1_compatibility_generator_delegates_to_canonical_active_generator() -> None:
    assert compatibility.STATUS_PATH == canonical.STATUS_PATH
    assert compatibility.CARD_PATH == canonical.CARD_PATH
    assert compatibility.MINI_PATH == canonical.MINI_PATH
    assert compatibility.COMPAT_CARD_PATH == canonical.COMPAT_CARD_PATH
    assert compatibility.COMPAT_MINI_PATH == canonical.COMPAT_MINI_PATH

    data = compatibility.parse_progress((ROOT / compatibility.STATUS_PATH).read_text(encoding="utf-8"))
    assert data.completed == 3
    assert data.total == 10
    assert data.display_percentage == "30.0%"
    assert compatibility.expected_outputs(data) == canonical.expected_outputs(data)
