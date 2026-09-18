from __future__ import annotations

from json import loads
from pathlib import Path
from subprocess import run
from sys import executable


REPOSITORY = Path(__file__).resolve().parents[1]
VERIFIER = REPOSITORY / "tools" / "verify_real_game_production_1_9.py"


def test_real_game_production_staging_covers_all_representative_games() -> None:
    result = run(
        [executable, str(VERIFIER), "--staging-only"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = loads(result.stdout)

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
        assert "scenes/title.swirscene" in exported
        assert "scenes/gameplay.swirscene" in exported
        assert fixture["source_runtime_ok"] is None
        assert fixture["staged_runtime_ok"] is None
        assert len(fixture["scene_fingerprint"]) == 64
        assert len(fixture["content_fingerprint"]) == 64
        assert len(fixture["export_manifest_sha256"]) == 64
        assert len(fixture["fingerprint"]) == 64

    assert "procedural_art.py" in fixtures["2d-game"]["exported_files"]
    assert "procedural_art.py" in fixtures["3d-game"]["exported_files"]


def test_multiplayer_game_demo_is_a_dedicated_source_fixture() -> None:
    run_game = REPOSITORY / "examples" / "multiplayer_game_demo" / "run_game.py"
    readme = REPOSITORY / "examples" / "multiplayer_game_demo" / "README.md"

    assert run_game.is_file()
    assert readme.is_file()
    source = run_game.read_text(encoding="utf-8")
    assert "run_multiplayer_soak" in source
    assert "NetworkImpairmentProfile" in source
    assert "seed=20260918" in source
