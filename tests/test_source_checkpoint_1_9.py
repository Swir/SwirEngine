from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_1_9_source_checkpoint.py"
ROADMAP = ROOT / "ROADMAP_1_9.md"
WORKFLOW = ROOT / ".github" / "workflows" / "source-checkpoint-1-9.yml"
READINESS = ROOT / "docs" / "SWIRENGINE_2_0_READINESS_AUDIT.md"

MILESTONE_RE = re.compile(r"^- \[([ xX])\] \*\*(\d+)\.", re.MULTILINE)
VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def run_auditor(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def roadmap_progress() -> tuple[int, int]:
    milestones = MILESTONE_RE.findall(ROADMAP.read_text(encoding="utf-8"))
    return sum(mark.lower() == "x" for mark, _ in milestones), len(milestones)


def test_development_checkpoint_audit_passes() -> None:
    result = run_auditor()
    assert result.returncode == 0, result.stdout + result.stderr
    completed, total = roadmap_progress()
    assert f"roadmap={completed}/{total}" in result.stdout
    assert "public-version=1.5.0" in result.stdout
    assert "2.0-readiness: N/A" in result.stdout


def test_strict_checkpoint_tracks_actual_roadmap_completion() -> None:
    completed, total = roadmap_progress()
    result = run_auditor("--require-complete")
    if completed == total == 10:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "mode=strict-complete" in result.stdout
    else:
        assert result.returncode != 0
        assert "refuses completion below 10/10 = 100.0%" in result.stdout


def test_roadmap_has_exactly_ten_ordered_milestones() -> None:
    milestones = MILESTONE_RE.findall(ROADMAP.read_text(encoding="utf-8"))
    assert len(milestones) == 10
    assert [int(number) for _, number in milestones] == list(range(1, 11))


def test_public_package_version_remains_frozen() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = VERSION_RE.search(pyproject)
    assert match is not None
    assert match.group(1) == "1.5.0"


def test_checkpoint_locks_real_game_and_prior_source_checkpoints() -> None:
    required = (
        "tools/verify_real_game_production_1_9.py",
        "tools/verify_clean_desktop_shipping_1_9.py",
        "tools/verify_1_6_source_checkpoint.py",
        "tools/verify_1_7_source_checkpoint.py",
        "tools/verify_1_8_source_checkpoint.py",
        ".github/workflows/showcase-hardening-1-4.yml",
        ".github/workflows/showcase-hardening-1-5.yml",
        ".github/workflows/source-checkpoint-1-6.yml",
        ".github/workflows/source-checkpoint-1-7.yml",
        ".github/workflows/source-checkpoint-1-8.yml",
    )
    assert all((ROOT / path).is_file() for path in required)


def test_readiness_audit_uses_evidence_and_no_fake_2_0_percentage() -> None:
    text = READINESS.read_text(encoding="utf-8")
    assert "## Verified 1.9 foundations" in text
    assert "## Evidence-backed gaps before 2.0" in text
    assert "## 2.0 readiness status" in text
    assert "N/A" in text
    assert "Release/PyPI: frozen until SwirEngine 2.0" in text
    assert re.search(r"2\.0 readiness[^\n]*\b\d+(?:\.\d+)?%", text, re.IGNORECASE) is None


def test_checkpoint_workflow_is_validation_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for token in (
        '"3.10"',
        '"3.13"',
        '"3.14"',
        "os: [ubuntu-latest, windows-latest, macos-latest]",
        "verify_1_8_source_checkpoint.py --require-complete",
        "generate_progress_svg.py --check",
        "python -m build",
        "python -m build --wheel --outdir wheelhouse",
        "twine check",
        "tests/test_shipping_1_9.py tests/test_exporting.py",
        "verify_real_game_production_1_9.py --staging-only",
        "verify_clean_desktop_shipping_1_9.py --wheelhouse wheelhouse",
    ):
        assert token in text

    lowered = text.lower()
    assert "twine upload" not in lowered
    assert "gh release" not in lowered
    assert "pypa/gh-action-pypi-publish" not in lowered
    assert "git tag" not in lowered


def test_no_dedicated_intermediate_19_release_workflow_exists() -> None:
    workflows = {path.name.lower() for path in (ROOT / ".github" / "workflows").glob("*.y*ml")}
    forbidden = {
        name
        for name in workflows
        if re.search(r"(?:release|publish|tag).*1[-_.]?9", name)
        or re.search(r"1[-_.]?9.*(?:release|publish|tag)", name)
    }
    assert forbidden == set()
