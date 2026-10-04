from __future__ import annotations

from pathlib import Path

import pytest

from tools.verify_2_2_release_readiness import (
    audit,
    parse_roadmap,
    require_phase_a_roadmap,
    validate_non_publishing_workflow,
    validate_readme,
)

ROOT = Path(__file__).resolve().parents[1]


WORKFLOW = ROOT / ".github/workflows/release-candidate-2.2.yml"


def test_repository_passes_2_2_phase_b_readiness() -> None:
    report = audit(ROOT)

    assert report.phase == "B"
    assert report.version == "2.2.0"
    assert report.roadmap.completed == 9
    assert report.roadmap.total == 10
    assert report.roadmap.percent == pytest.approx(90.0)
    assert len(report.checks) >= 15


def test_pre_release_rejects_closing_milestone_10_early() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    closed = roadmap.replace(
        "- [ ] **10. Production acceptance and 2.2 release readiness.**",
        "- [x] **10. Production acceptance and 2.2 release readiness.**",
        1,
    ).replace(
        "Current verified progress: 9/10 milestones = 90.0%.",
        "Current verified progress: 10/10 milestones = 100.0%.",
        1,
    )

    with pytest.raises(AssertionError, match="remain exactly 9/10"):
        require_phase_a_roadmap(closed, parse_roadmap(closed))


def test_pre_release_rejects_missing_or_renumbered_milestone() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    broken = roadmap.replace(
        "- [ ] **10. Production acceptance and 2.2 release readiness.**",
        "- [ ] **11. Production acceptance and 2.2 release readiness.**",
        1,
    )

    with pytest.raises(AssertionError, match="exactly ten contiguous"):
        parse_roadmap(broken)


def test_readme_rejects_advertising_unpublished_2_2_install() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    broken = readme.replace('"swirengine==2.1.0"', '"swirengine==2.2.0"', 1)

    with pytest.raises(AssertionError, match="README"):
        validate_readme(broken, state, root=ROOT)


def test_readme_rejects_progress_drift() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    broken = readme.replace("Counter: 9 / 10 milestones", "Counter: 10 / 10 milestones", 1)

    with pytest.raises(AssertionError, match="exactly match"):
        validate_readme(broken, state, root=ROOT)


@pytest.mark.parametrize(
    "forbidden",
    [
        "contents: write",
        "id-token: write",
        "pypa/gh-action-pypi-publish@release/v1",
        "gh release create v2.2.0",
        "git push origin v2.2.0",
    ],
)
def test_readiness_workflow_rejects_publish_capability(forbidden: str) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    with pytest.raises(AssertionError, match="forbidden publishing capability"):
        validate_non_publishing_workflow(f"{workflow}\n# mutation\n{forbidden}\n")


def test_readiness_workflow_rejects_implicit_checkout_identity() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    broken = workflow.replace(
        "github.event.pull_request.head.sha",
        "github.sha",
        1,
    )

    with pytest.raises(AssertionError, match="exact-source gate"):
        validate_non_publishing_workflow(broken)


def test_candidate_workflow_keeps_full_supported_matrix_and_candidate_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for runner in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert runner in workflow
    for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
        assert f'"{version}"' in workflow
    assert workflow.count("--expected-version 2.2.0") == 2
    assert "persist-credentials: false" in workflow
    assert "id-token: write" not in workflow


def test_candidate_workflow_rejects_missing_same_repository_binding() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    broken = workflow.replace("Swir/SwirEngine", "example/fork", 1)

    with pytest.raises(AssertionError, match="exact-source gate"):
        validate_non_publishing_workflow(broken, phase="B")
