from importlib.metadata import metadata, version
from pathlib import Path

import swirengine


def test_package_version_matches_installed_metadata():
    assert swirengine.__version__ == version("swirengine")


def test_public_api_exports_are_unique_and_resolvable():
    assert len(swirengine.__all__) == len(set(swirengine.__all__))
    missing = [name for name in swirengine.__all__ if not hasattr(swirengine, name)]
    assert missing == []


def test_stable_patch_release_version():
    assert swirengine.__version__ == "1.0.2"


def test_supported_python_range_is_explicit():
    requires_python = metadata("swirengine")["Requires-Python"]
    assert {item.strip() for item in requires_python.split(",")} == {">=3.10", "<3.14"}


def test_readme_tracks_current_release_and_support_window():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert f"# SwirEngine {swirengine.__version__}" in readme
    assert "Python 3.10-3.13" in readme
    assert "shadows, post-processing" in readme
    assert "remain roadmap work" not in readme
