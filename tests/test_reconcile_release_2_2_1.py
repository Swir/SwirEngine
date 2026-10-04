from __future__ import annotations

import pytest

from tools.reconcile_release_2_2_1 import (
    ArtifactIdentity,
    ExpectedRelease,
    ReleaseReconciliationError,
    ReleaseSnapshot,
    reconcile_release,
)

PUBLICATION = "3" * 40
DESCRIPTION = "# SwirEngine 2.2.1\n\nDetailed description.\n"


def _expected() -> ExpectedRelease:
    distribution = ArtifactIdentity(
        name="swirengine-2.2.1-py3-none-any.whl",
        sha256="a" * 64,
        size=10,
    )
    return ExpectedRelease(
        publication_commit=PUBLICATION,
        release_title="SwirEngine 2.2.1",
        release_body="# SwirEngine 2.2.1 Release Notes\n",
        pypi_description=DESCRIPTION,
        distributions=(distribution,),
        release_assets=(distribution,),
    )


def _pypi(*, description: str = DESCRIPTION) -> dict[str, object]:
    return {
        "info": {
            "name": "swirengine",
            "version": "2.2.1",
            "description": description,
            "description_content_type": "text/markdown",
            "requires_python": ">=3.10,<3.15",
        },
        "urls": [
            {
                "filename": "swirengine-2.2.1-py3-none-any.whl",
                "digests": {"sha256": "a" * 64},
                "size": 10,
                "yanked": False,
            }
        ],
    }


def test_exact_pypi_metadata_is_accepted() -> None:
    plan = reconcile_release(
        _expected(),
        ReleaseSnapshot(pypi=_pypi(), tag=None, release=None),
    )

    assert plan.pypi_uploads == ()
    assert plan.create_tag is True
    assert plan.create_release is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("description", "different", "description does not match"),
        ("description_content_type", "text/plain", "description_content_type"),
        ("requires_python", ">=3.11", "Requires-Python"),
    ],
)
def test_pypi_metadata_drift_fails_closed(field: str, value: str, message: str) -> None:
    payload = _pypi()
    payload["info"][field] = value  # type: ignore[index]

    with pytest.raises(ReleaseReconciliationError, match=message):
        reconcile_release(
            _expected(),
            ReleaseSnapshot(pypi=payload, tag=None, release=None),
        )


def test_absent_public_state_plans_only_expected_objects() -> None:
    expected = _expected()
    plan = reconcile_release(expected, ReleaseSnapshot(pypi=None, tag=None, release=None))

    assert plan.pypi_uploads == ("swirengine-2.2.1-py3-none-any.whl",)
    assert plan.github_uploads == ("swirengine-2.2.1-py3-none-any.whl",)
    assert plan.create_tag is True
    assert plan.create_release is True
