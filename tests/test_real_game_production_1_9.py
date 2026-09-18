from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
VERIFIER = REPOSITORY / "tools" / "verify_real_game_production_1_9.py"
MULTIPLAYER_DEMO = REPOSITORY / "examples" / "multiplayer_game_demo" / "run_game.py"


def test_real_game_production_staging_covers_all_representative_games() -> None:
    result = subprocess.run(
        [sys.executable, str(VERIFIER), "--staging-only"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)

    assert report["status"] == "ok"
    assert report["scope"] == "SwirEngine 1.9 Real-Game Production Gate"
    assert report["runtime_validation"] is False
    assert report["fixture_count"] == 3

    fixtures = {item["name"]: item for item in report["fixtures"]}
    assert set(fixtures) == {"2d-game", "3d-game", "multiplayer-game"}
    for fixture in fixtures.values():
        exported = set(fixture["exported_files"])
        assert "run_game.py" in exported
        assert "swirproject.toml" in exported
        assert "assets/fixture.txt" in exported
        assert "config/controls.json" in exported
        assert "config/settings.json" in exported
        assert "scenes/title.swirscene" in exported
        assert "scenes/gameplay.swirscene" in exported
        assert not any(path.startswith("user-data/") for path in exported)
        assert fixture["source_runtime_ok"] is None
        assert fixture["staged_runtime_ok"] is None
        for fingerprint_name in (
            "scene_fingerprint",
            "content_fingerprint",
            "input_fingerprint",
            "settings_fingerprint",
            "game_state_fingerprint",
            "export_manifest_sha256",
            "fingerprint",
        ):
            assert len(fixture[fingerprint_name]) == 64

    assert "procedural_art.py" in fixtures["2d-game"]["exported_files"]
    assert "procedural_art.py" in fixtures["3d-game"]["exported_files"]


def test_multiplayer_game_demo_is_a_dedicated_source_fixture() -> None:
    readme = REPOSITORY / "examples" / "multiplayer_game_demo" / "README.md"

    assert MULTIPLAYER_DEMO.is_file()
    assert readme.is_file()
    source = MULTIPLAYER_DEMO.read_text(encoding="utf-8")
    assert "run_multiplayer_soak" in source
    assert "NetworkImpairmentProfile" in source
    assert "seed=20260918" in source


def test_multiplayer_game_demo_runs_with_numeric_client_timelines() -> None:
    result = subprocess.run(
        [sys.executable, str(MULTIPLAYER_DEMO)],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    json_start = result.stdout.find("{")
    assert json_start >= 0, result.stdout
    report = json.loads(result.stdout[json_start:])

    final_ticks = report["final_client_ticks"]
    assert isinstance(final_ticks, dict)
    assert len(final_ticks) == report["clients"] == 4
    assert all(isinstance(client_id, str) and client_id for client_id in final_ticks)
    assert all(isinstance(tick, int) and tick > 0 for tick in final_ticks.values())
    assert report["applied_updates"] > 0
    assert len(report["fingerprint"]) == 64
