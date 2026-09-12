from importlib.metadata import version

import swirengine


def test_runtime_version_matches_installed_package_metadata():
    assert swirengine.__version__ == version("swirengine")
