from __future__ import annotations

from tools.verify_public_release_2_1 import (
    EXPECTED_RELEASE_ASSETS,
    EXPECTED_SOURCE_SHA,
    validate_github_state,
    validate_pypi_metadata,
)


def _pypi(requires_python: str = "<3.15,>=3.10") -> dict[str, object]:
    return {
        "info": {"version": "2.1.0", "requires_python": requires_python},
        "urls": [
            {"filename": "swirengine-2.1.0-py3-none-any.whl"},
            {"filename": "swirengine-2.1.0-cp314-cp314-win_amd64.whl"},
            {"filename": "swirengine-2.1.0.tar.gz"},
        ],
    }


def _tag(sha: str = EXPECTED_SOURCE_SHA) -> dict[str, object]:
    return {"object": {"type": "commit", "sha": sha}}


def _release() -> dict[str, object]:
    return {
        "tag_name": "v2.1.0",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in sorted(EXPECTED_RELEASE_ASSETS)],
    }


def test_pypi_requires_python_comparison_is_order_insensitive() -> None:
    assert validate_pypi_metadata(_pypi("<3.15,>=3.10")) == []
    assert validate_pypi_metadata(_pypi(">=3.10, <3.15")) == []


def test_pypi_rejects_semantic_python_range_drift() -> None:
    errors = validate_pypi_metadata(_pypi(">=3.11,<3.15"))
    assert any("differs semantically" in error for error in errors)


def test_pypi_rejects_missing_distribution() -> None:
    payload = _pypi()
    payload["urls"] = payload["urls"][:-1]  # type: ignore[index]
    errors = validate_pypi_metadata(payload)
    assert any("missing distributions" in error for error in errors)


def test_github_state_accepts_exact_immutable_release() -> None:
    assert validate_github_state(_tag(), _release(), EXPECTED_SOURCE_SHA) == []


def test_github_state_rejects_wrong_tag_target_and_missing_asset() -> None:
    release = _release()
    release["assets"] = release["assets"][:-1]  # type: ignore[index]
    errors = validate_github_state(_tag("0" * 40), release, EXPECTED_SOURCE_SHA)
    assert any("does not resolve" in error for error in errors)
    assert any("missing assets" in error for error in errors)
