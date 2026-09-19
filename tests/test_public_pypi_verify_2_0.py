from __future__ import annotations

from pathlib import Path

import pytest

from tools.verify_public_pypi_2_0 import (
    EXPECTED_REQUIRES_PYTHON,
    SIMPLE_URL,
    VERSION,
    public_install_command,
    retry,
    validate_metadata,
)


def test_public_install_command_is_exact_public_index_only() -> None:
    command = public_install_command(Path("python"))

    assert command == [
        "python",
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        "--index-url",
        SIMPLE_URL,
        f"swirengine=={VERSION}",
    ]
    assert "--find-links" not in command
    assert "--extra-index-url" not in command


def test_retry_recovers_transient_propagation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("simple index not propagated yet")
        return "ok"

    monkeypatch.setattr("tools.verify_public_pypi_2_0.time.sleep", sleeps.append)

    assert retry(operation, attempts=4, delay=2.5) == "ok"
    assert calls == 3
    assert sleeps == [2.5, 2.5]


def test_retry_fails_closed_after_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("still unavailable")

    monkeypatch.setattr("tools.verify_public_pypi_2_0.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="still unavailable"):
        retry(operation, attempts=3, delay=1.0)
    assert calls == 3


def test_metadata_contract_matches_public_2_0_support_bounds() -> None:
    validate_metadata(
        {
            "info": {
                "version": VERSION,
                "requires_python": ",".join(sorted(EXPECTED_REQUIRES_PYTHON)),
            }
        }
    )


def test_metadata_contract_rejects_wrong_version_or_python_bounds() -> None:
    with pytest.raises(ValueError, match="unexpected public version"):
        validate_metadata({"info": {"version": "1.5.0", "requires_python": ">=3.10,<3.15"}})

    with pytest.raises(ValueError, match="unexpected requires_python"):
        validate_metadata({"info": {"version": VERSION, "requires_python": ">=3.11,<3.15"}})
