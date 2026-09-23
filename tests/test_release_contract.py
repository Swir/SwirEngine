from importlib.metadata import metadata, version
from pathlib import Path

import swirengine

PUBLIC_STABLE_VERSION = "2.0.0"
CANDIDATE_VERSION = "2.1.0"


def _allowed_source_versions() -> set[str]:
    roadmap_20 = Path("ROADMAP_2_0.md").read_text(encoding="utf-8")
    final_complete = "- [x] **10. SwirEngine 2.0 Final Release Gate & Public Verification**" in roadmap_20
    if not final_complete:
        return {"1.5.0"}

    allowed = {PUBLIC_STABLE_VERSION}
    roadmap_21 = Path("ROADMAP_2_1.md")
    notes_21 = Path("RELEASE_NOTES_2_1.md")
    gate_21 = Path("docs/RELEASE_GATE_2_1.md")
    if roadmap_21.is_file() and notes_21.is_file() and gate_21.is_file():
        roadmap_text = roadmap_21.read_text(encoding="utf-8")
        notes_text = notes_21.read_text(encoding="utf-8")
        gate_text = gate_21.read_text(encoding="utf-8")
        readme_text = Path("README.md").read_text(encoding="utf-8")
        accepted_21 = (
            "Current verified progress: 10/10 milestones = 100.0%." in roadmap_text
            and "## Phase C — publication decision" in gate_text
        )
        candidate_21 = "NOT PUBLISHED" in notes_text
        published_21 = (
            notes_text.startswith("# SwirEngine 2.1.0 Release Notes")
            and "**Latest public stable release:** **SwirEngine 2.1.0**" in readme_text
        )
        if accepted_21 and (candidate_21 or published_21):
            allowed.add(CANDIDATE_VERSION)
    return allowed


def test_package_version_matches_installed_metadata():
    assert swirengine.__version__ == version("swirengine")


def test_public_api_exports_are_unique_and_resolvable():
    assert len(swirengine.__all__) == len(set(swirengine.__all__))
    missing = [name for name in swirengine.__all__ if not hasattr(swirengine, name)]
    assert missing == []


def test_source_version_matches_guarded_release_phase():
    allowed = _allowed_source_versions()
    assert swirengine.__version__ in allowed
    if swirengine.__version__ == CANDIDATE_VERSION:
        readme = Path("README.md").read_text(encoding="utf-8")
        notes = Path("RELEASE_NOTES_2_1.md").read_text(encoding="utf-8")
        if "NOT PUBLISHED" in notes:
            assert "**Latest public stable release:** **SwirEngine 2.0.0**" in readme
            assert "swirengine==2.1.0" not in readme
        else:
            assert "**Latest public stable release:** **SwirEngine 2.1.0**" in readme
            assert 'swirengine==2.1.0' in readme


def test_supported_python_range_is_explicit():
    requires_python = metadata("swirengine")["Requires-Python"]
    assert {item.strip() for item in requires_python.split(",")} == {">=3.10", "<3.15"}


def test_readme_preserves_locked_1_5_evidence_after_2_0_publication():
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap_15 = Path("ROADMAP_1_5.md").read_text(encoding="utf-8")
    notes_15 = Path("RELEASE_NOTES_1_5.md").read_text(encoding="utf-8")

    assert "<!-- SWIR-README-STANDARD:v2 -->" in readme
    assert "`v1.5.0`" in readme
    assert "| 1.5 |" in readme
    assert "released/locked" in readme
    if swirengine.__version__ in {PUBLIC_STABLE_VERSION, CANDIDATE_VERSION}:
        assert "`v2.0.0`" in readme or "| 2.0 |" in readme
        if swirengine.__version__ == CANDIDATE_VERSION and "NOT PUBLISHED" not in Path(
            "RELEASE_NOTES_2_1.md"
        ).read_text(encoding="utf-8"):
            assert "**Latest public stable release:** **SwirEngine 2.1.0**" in readme
        else:
            assert "**Latest public stable release:** **SwirEngine 2.0.0**" in readme
        assert "64-bit CPython 3.10–3.14" in readme
        assert "Windows, Linux and macOS" in readme
    else:
        assert "STATUS-1.5.0%20STABLE" in readme
        assert "Python 3.10-3.13" in readme
        assert "Python 3.14 on Windows x86-64" in readme
    assert "gamepad" in readme.lower()
    for historical_feature in (
        "Deterministic Simulation & Replay",
        "Save & Profile 2.0",
        "World Streaming 2.0",
        "UI Toolkit 2.0",
        "Runtime Diagnostics & Profiling 2.0",
    ):
        assert historical_feature in roadmap_15 or historical_feature in notes_15
    assert "Neon Frontier 1.4" in readme
    assert "10/10 = 100.0%" in readme
    assert "remain roadmap work" not in readme
