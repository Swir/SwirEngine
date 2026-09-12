import re
from pathlib import Path

import swirengine


def test_runtime_version_matches_project_metadata():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE)
    assert match is not None
    assert swirengine.__version__ == match.group(1)
