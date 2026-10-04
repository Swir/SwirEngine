from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "demo_projects" / "ShadowRelic32_32bit" / "main.py"
        if candidate.is_file():
            return parent
    raise AssertionError("repository root containing ShadowRelic32_32bit was not found")


def test_shadow_relic_32_headless_engine_probe() -> None:
    repo = _repo_root()
    demo = repo / "demo_projects" / "ShadowRelic32_32bit"
    env = os.environ.copy()
    env["SHADOW_RELIC_HEADLESS"] = "1"
    env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, str(demo / "main.py")],
        cwd=demo,
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Shadow Relic 32 headless OK" in completed.stdout
    assert "engine_physics" in completed.stdout


def test_shadow_relic_32_art_generator(tmp_path: Path) -> None:
    repo = _repo_root()
    demo = repo / "demo_projects" / "ShadowRelic32_32bit"
    env = os.environ.copy()
    env["SHADOW_RELIC_ASSET_CACHE"] = str(tmp_path / "assets")
    completed = subprocess.run(
        [sys.executable, str(demo / "procedural_art.py")],
        cwd=demo,
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assets = tmp_path / "assets"
    assert (assets / "hero_idle0_r.png").is_file()
    assert (assets / "warden0_r.png").is_file()
    assert (assets / "shadow_relic_32.ico").is_file()
