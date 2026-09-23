from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/release-2.0.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_historical_2_0_publication_keeps_trusted_publisher_contract() -> None:
    workflow = _workflow()
    trigger = workflow.split("jobs:", 1)[0]

    assert "name: Release 2.0" in trigger
    assert "workflow_dispatch:" in trigger
    assert 'tags:\n      - "v2.0.0"' in trigger
    assert "environment: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow


def test_historical_2_0_publication_is_bound_to_immutable_tag_source() -> None:
    workflow = _workflow()

    assert workflow.count('ref: "refs/tags/v2.0.0"') >= 4
    assert "verify_2_0_release_candidate.py --require-final" in workflow
    assert "verify_2_0_public_api.py" in workflow
    assert "verify_platform_matrix_2_0.py" in workflow
    assert "verify_real_game_shipping_2_0.py" in workflow
    assert "verify_performance_evidence_2_0.py --validate-only" in workflow
    assert "verify_release_safety_2_0.py" in workflow
    assert "verify_packaging_shipping_2_0.py" in workflow
    assert 'actual != f"v{version}"' in workflow
    assert "tag_commit != head_commit" in workflow


def test_historical_2_0_publication_never_rewrites_public_history() -> None:
    workflow = _workflow()

    assert "Refuse to replace an existing release" in workflow
    assert "git push --force" not in workflow
    assert "git tag -f" not in workflow
    assert "skip-existing: true" not in workflow
    assert "password:" not in workflow
    assert "PYPI_API_TOKEN" not in workflow


def test_historical_2_0_publication_revalidates_shipping_and_public_installation() -> None:
    workflow = _workflow()

    assert "xvfb-run -a python examples/2d_game_demo/run_game.py" in workflow
    assert "xvfb-run -a python examples/3d_game_demo/run_game.py" in workflow
    assert "PyInstaller" in workflow
    assert "build_vendored_wheel.py" in workflow
    assert "cp314-cp314-win_amd64" in workflow
    assert "swirengine==2.0.0" in workflow
    assert '"--index-url",' in workflow
    assert '"https://pypi.org/simple",' in workflow
    assert "github-release:" in workflow
    assert workflow.index("pypi-publish:") < workflow.index("github-release:")
    assert "post-release-public-pypi:" in workflow
    assert 'python-version: "3.14"' in workflow
