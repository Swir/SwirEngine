from __future__ import annotations

from pathlib import Path

import pytest

from tools.verify_2_2_release_readiness import (
    audit,
    parse_roadmap,
    require_phase_a_roadmap,
    require_phase_e_roadmap,
    validate_non_publishing_workflow,
    validate_post_release_workflow,
    validate_readme,
)

ROOT = Path(__file__).resolve().parents[1]


WORKFLOW = ROOT / "tests/fixtures/release-candidate-2.2.yml"
POST_RELEASE_WORKFLOW = ROOT / ".github/workflows/post-release-2.2.yml"


def test_repository_passes_2_2_release_or_patch_readiness() -> None:
    report = audit(ROOT)

    assert (report.phase, report.version) in {("E", "2.2.0"), ("PATCH", "2.2.1")}
    assert report.roadmap.completed == 10
    assert report.roadmap.total == 10
    assert report.roadmap.percent == pytest.approx(100.0)
    assert len(report.checks) >= 15


def test_historical_pre_release_rejects_closed_milestone_10() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")

    with pytest.raises(AssertionError, match="remain exactly 9/10"):
        require_phase_a_roadmap(roadmap, parse_roadmap(roadmap))


def test_phase_e_rejects_reopening_milestone_10() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    reopened = roadmap.replace(
        "- [x] **10. Production acceptance and 2.2 release readiness.**",
        "- [ ] **10. Production acceptance and 2.2 release readiness.**",
        1,
    ).replace(
        "Current verified progress: 10/10 milestones = 100.0%.",
        "Current verified progress: 9/10 milestones = 90.0%.",
        1,
    )

    with pytest.raises(AssertionError, match="exactly 10/10"):
        require_phase_e_roadmap(reopened, parse_roadmap(reopened))


def test_pre_release_rejects_missing_or_renumbered_milestone() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    broken = roadmap.replace(
        "- [x] **10. Production acceptance and 2.2 release readiness.**",
        "- [x] **11. Production acceptance and 2.2 release readiness.**",
        1,
    )

    with pytest.raises(AssertionError, match="exactly ten contiguous"):
        parse_roadmap(broken)


def test_readme_phase_e_rejects_reverting_public_install_to_2_1() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    broken = readme.replace('"swirengine==2.2.0"', '"swirengine==2.1.0"', 1)

    with pytest.raises(AssertionError, match="Phase E contract"):
        validate_readme(broken, state, root=ROOT, phase="E")


def test_readme_accepts_bound_2_2_1_patch_candidate_over_public_2_2_0() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "bound non-publishing patch candidate" not in readme.casefold():
        readme += (
            "\nSwirEngine 2.2.1 is the bound non-publishing patch candidate. "
            "It is NOT PUBLISHED.\n"
        )

    validate_readme(readme, state, root=ROOT, phase="PATCH")


def test_readme_patch_candidate_rejects_public_2_2_1_install_pin() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "bound non-publishing patch candidate" not in readme.casefold():
        readme += (
            "\nSwirEngine 2.2.1 is the bound non-publishing patch candidate. "
            "It is NOT PUBLISHED.\n"
        )
    broken = readme + '\npython -m pip install -U "swirengine==2.2.1"\n'

    with pytest.raises(AssertionError, match="must not advertise a public 2.2.1 install"):
        validate_readme(broken, state, root=ROOT, phase="PATCH")


def test_readme_rejects_progress_drift() -> None:
    roadmap = (ROOT / "ROADMAP_2_2.md").read_text(encoding="utf-8")
    state = parse_roadmap(roadmap)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    broken = readme.replace("Counter: 10 / 10 milestones", "Counter: 9 / 10 milestones", 1)

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


def test_post_release_workflow_is_exact_source_and_read_only() -> None:
    workflow = POST_RELEASE_WORKFLOW.read_text(encoding="utf-8")

    validate_post_release_workflow(workflow)


def test_post_release_workflow_rejects_publish_capability() -> None:
    workflow = POST_RELEASE_WORKFLOW.read_text(encoding="utf-8")

    with pytest.raises(AssertionError, match="forbidden publishing capability"):
        validate_post_release_workflow(f"{workflow}\npermissions: contents: write\n")
