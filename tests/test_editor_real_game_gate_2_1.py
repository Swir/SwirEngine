from __future__ import annotations

import json
import subprocess
import sys


_EXPECTED_FIXTURES = ["2d-game", "3d-game", "multiplayer-game"]


def _assert_sha256(value: object) -> None:
    assert isinstance(value, str)
    assert len(value) == 64
    assert all(character in "0123456789abcdef" for character in value)


def test_milestone_10_real_game_editor_gate() -> None:
    result = subprocess.run(
        [sys.executable, "tools/verify_editor_real_game_gate_2_1.py"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)

    assert report["status"] == "ok"
    assert report["scope"] == "SwirEngine 2.1 Milestone 10 Real-Game Editor Gate"
    assert report["fixture_count"] == 3
    assert report["fixture_names"] == _EXPECTED_FIXTURES
    assert report["host_target"] in {"windows", "linux", "macos"}
    _assert_sha256(report["fingerprint"])

    fixtures = report["fixtures"]
    assert [item["name"] for item in fixtures] == _EXPECTED_FIXTURES
    for item in fixtures:
        assert item["mode"] in {"2d", "3d"}
        assert item["editor_save_reopen"] is True
        assert item["editor_preview_ok"] is True
        assert item["profile_roundtrip"] is True
        assert item["planned_file_count"] == item["staged_file_count"]
        assert item["staged_file_count"] > 0
        assert item["checksums_verified"] is True
        assert item["source_runtime_ok"] is True
        assert item["staged_runtime_ok"] is True
        _assert_sha256(item["fingerprint"])
