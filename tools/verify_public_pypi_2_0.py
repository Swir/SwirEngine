from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import venv
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

VERSION = "2.0.0"
JSON_URL = f"https://pypi.org/pypi/swirengine/{VERSION}/json"
SIMPLE_URL = "https://pypi.org/simple"
EXPECTED_REQUIRES_PYTHON = {">=3.10", "<3.15"}

T = TypeVar("T")


def retry(operation: Callable[[], T], *, attempts: int, delay: float) -> T:
    """Run a bounded retry loop without converting a persistent failure into success."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - bounded retry must preserve the final exception
            last_error = exc
            if attempt == attempts:
                raise
            if delay:
                time.sleep(delay)
    assert last_error is not None
    raise last_error


def fetch_public_metadata(*, attempts: int, delay: float) -> dict[str, object]:
    def fetch() -> dict[str, object]:
        try:
            with urllib.request.urlopen(JSON_URL, timeout=20) as response:
                payload = json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            raise
        if not isinstance(payload, dict):
            raise ValueError("PyPI metadata response is not an object")
        return payload

    return retry(fetch, attempts=attempts, delay=delay)


def validate_metadata(metadata: dict[str, object]) -> None:
    info = metadata.get("info")
    if not isinstance(info, dict):
        raise ValueError("PyPI metadata has no info object")
    version = info.get("version")
    if version != VERSION:
        raise ValueError(f"unexpected public version: {version!r}")
    requires_python = info.get("requires_python")
    if not isinstance(requires_python, str):
        raise ValueError("PyPI metadata has no requires_python string")
    normalized = {part.strip() for part in requires_python.split(",")}
    if normalized != EXPECTED_REQUIRES_PYTHON:
        raise ValueError(f"unexpected requires_python: {requires_python!r}")


def public_install_command(python: Path) -> list[str]:
    return [
        str(python),
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        "--index-url",
        SIMPLE_URL,
        f"swirengine=={VERSION}",
    ]


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def verify_public_install(*, attempts: int, delay: float) -> None:
    """Verify a clean install from the public Simple index, retrying propagation races only."""
    with tempfile.TemporaryDirectory(prefix="swir-public-2.0-") as temp:
        root = Path(temp)
        env_dir = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        python = _venv_python(env_dir)

        subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])

        def install() -> None:
            subprocess.check_call(public_install_command(python), cwd=root)

        retry(install, attempts=attempts, delay=delay)

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        subprocess.check_call(
            [
                str(python),
                "-c",
                (
                    "import swirengine; "
                    f"assert swirengine.__version__ == '{VERSION}'; "
                    "print(swirengine.__file__)"
                ),
            ],
            cwd=root,
            env=env,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify SwirEngine 2.0.0 from public PyPI with bounded propagation retries"
    )
    parser.add_argument("--attempts", type=int, default=24)
    parser.add_argument("--delay", type=float, default=10.0)
    args = parser.parse_args(argv)

    metadata = fetch_public_metadata(attempts=args.attempts, delay=args.delay)
    validate_metadata(metadata)
    verify_public_install(attempts=args.attempts, delay=args.delay)
    print(f"verified public PyPI release: swirengine=={VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
