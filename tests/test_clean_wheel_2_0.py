from __future__ import annotations

from pathlib import Path

import pytest

import tools.verify_clean_wheel_2_0 as clean_wheel
from tools.verify_clean_wheel_2_0 import build_parser, resolve_expected_version


def test_expected_version_is_optional_for_legacy_platform_calls() -> None:
    assert resolve_expected_version(None, verify_cli21=False) is None


def test_legacy_cli21_call_keeps_2_1_0_version_assertion() -> None:
    assert resolve_expected_version(None, verify_cli21=True) == "2.1.0"


@pytest.mark.parametrize("expected", ["2.1.0", "2.2.0", "2.2.0rc1", "12.34.56+local"])
def test_explicit_expected_version_is_preserved(expected: str) -> None:
    assert resolve_expected_version(expected, verify_cli21=False) == expected


@pytest.mark.parametrize(
    "expected",
    ["", "2.1", "v2.1.0", "2.1.0 ", "2.1.0; import os", "latest"],
)
def test_invalid_expected_version_fails_closed(expected: str) -> None:
    with pytest.raises(ValueError, match="explicit normalized"):
        resolve_expected_version(expected, verify_cli21=False)


def test_parser_accepts_phase_a_exact_version_without_changing_cli_flag() -> None:
    args = build_parser().parse_args(
        [
            "--wheel-dir",
            "dist",
            "--expected-system",
            "Linux",
            "--expected-python",
            "3.13",
            "--expected-version",
            "2.1.0",
        ]
    )

    assert args.expected_version == "2.1.0"
    assert args.verify_cli21 is False


def test_version_probe_passes_expected_value_as_data(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, str] | None, Path | None]] = []

    def capture(
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        calls.append((command, env, cwd))

    monkeypatch.setattr(clean_wheel, "_run", capture)
    clean_wheel._verify_installed_version(
        Path("python"),
        "2.1.0",
        env={"SAFE": "1"},
        cwd=Path("clean-root"),
    )

    assert len(calls) == 1
    command, env, cwd = calls[0]
    assert command[:2] == ["python", "-c"]
    assert command[-1] == "2.1.0"
    assert "sys.argv[1]" in command[2]
    assert env == {"SAFE": "1"}
    assert cwd == Path("clean-root")
