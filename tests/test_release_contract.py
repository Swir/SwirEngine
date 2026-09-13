import tomllib
from pathlib import Path

import swirengine


ROOT = Path(__file__).resolve().parents[1]


def test_package_version_matches_project_metadata():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert swirengine.__version__ == project["version"]


def test_public_api_exports_are_unique_and_resolvable():
    assert len(swirengine.__all__) == len(set(swirengine.__all__))
    missing = [name for name in swirengine.__all__ if not hasattr(swirengine, name)]
    assert missing == []


def test_first_stable_release_version():
    assert swirengine.__version__ == "1.0.0"
