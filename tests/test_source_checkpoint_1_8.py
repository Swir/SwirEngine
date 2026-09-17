from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_1_8_source_checkpoint.py"
ROADMAP = ROOT / "ROADMAP_1_8.md"

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


def test_checkpoint_requires_real_rendering_stack_and_closeout_assets() -> None:
    required = (
        "src/swirengine/render_graph18.py",
        "src/swirengine/render_resources18.py",
        "src/swirengine/render_uploads18.py",
        "src/swirengine/render_submission18.py",
        "src/swirengine/visibility18.py",
        "src/swirengine/render_timing18.py",
        "src/swirengine/render_quality18.py",
        "src/swirengine/renderer2_bridge18.py",
        "src/swirengine/render_showcase18.py",
        "docs/RELEASE_HARDENING_1_8.md",
        ".github/workflows/source-checkpoint-1-8.yml",
    )
    assert all((ROOT / path).is_file() for path in required)


def test_no_dedicated_intermediate_18_release_workflow_exists() -> None:
    workflows = {path.name.lower() for path in (ROOT / ".github" / "workflows").glob("*.y*ml")}
    forbidden = {
        name
        for name in workflows
        if re.search(r"(?:release|publish|tag).*1[-_.]?8", name)
        or re.search(r"1[-_.]?8.*(?:release|publish|tag)", name)
    }
    assert forbidden == set()
