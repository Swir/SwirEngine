from __future__ import annotations

import json
import subprocess
import sys


def _assert_sha256(value: str) -> None:
    assert len(value) == 64
    assert all(character in "0123456789abcdef" for character in value)


def test_real_game_shipping_gate_staging_contract():
    result = subprocess.run(
        [sys.executable, "tools/verify_real_game_shipping_2_0.py", "--staging-only"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert report["scope"] == "SwirEngine 2.0 Representative Real-Game Shipping Gate"
    assert report["fixture_count"] == 3
    assert report["fixture_names"] == ["2d-game", "3d-game", "multiplayer-game"]
    assert report["runtime_validation"] is False
    assert report["player_data_boundary"] == "external-to-shipping-content"
    assert report["failure_paths"] == {
        "missing_asset_rejected": True,
        "missing_entrypoint_rejected": True,
        "missing_scene_rejected": True,
    }
    assert report["ui_navigation"] == {
        "2d-game": True,
        "3d-game": True,
        "multiplayer-game": True,
    }
    _assert_sha256(report["production_fingerprint"])
    diagnostics = report["diagnostic_fingerprints"]
    assert sorted(diagnostics) == ["2d-game", "3d-game", "multiplayer-game"]
    for fingerprint in diagnostics.values():
        _assert_sha256(fingerprint)
