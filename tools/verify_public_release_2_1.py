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
from collections.abc import Mapping
from typing import Any

VERSION = "2.1.0"
TAG = "v2.1.0"
EXPECTED_SOURCE_SHA = "f241d61bad54a87df1554b306bffea3d6cc7d624"
EXPECTED_REQUIRES_PYTHON = frozenset({">=3.10", "<3.15"})
EXPECTED_DISTRIBUTIONS = frozenset(
    {
        "swirengine-2.1.0-py3-none-any.whl",
        "swirengine-2.1.0-cp314-cp314-win_amd64.whl",
        "swirengine-2.1.0.tar.gz",
    }
)
EXPECTED_RELEASE_ASSETS = EXPECTED_DISTRIBUTIONS | frozenset(
    {"SHA256SUMS", "release-provenance.json"}
)


def normalize_specifiers(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def validate_pypi_metadata(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    info = payload.get("info")
    if not isinstance(info, Mapping):
        return ["PyPI response has no info object"]

    if info.get("version") != VERSION:
        errors.append(f"PyPI version is {info.get('version')!r}, expected {VERSION!r}")

    requires_python = info.get("requires_python")
    if not isinstance(requires_python, str):
        errors.append("PyPI requires_python is missing")
    elif normalize_specifiers(requires_python) != EXPECTED_REQUIRES_PYTHON:
        errors.append(
            "PyPI requires_python differs semantically: "
            f"{requires_python!r} != {sorted(EXPECTED_REQUIRES_PYTHON)!r}"
        )

    urls = payload.get("urls")
    filenames = {
        item.get("filename")
        for item in urls
        if isinstance(urls, list) and isinstance(item, Mapping)
    } if isinstance(urls, list) else set()
    missing = EXPECTED_DISTRIBUTIONS - filenames
    if missing:
        errors.append(f"PyPI is missing distributions: {sorted(missing)!r}")
    return errors


def validate_github_state(
    tag_payload: Mapping[str, Any], release_payload: Mapping[str, Any], expected_sha: str
) -> list[str]:
    errors: list[str] = []
    tag_object = tag_payload.get("object")
    tag_sha = tag_object.get("sha") if isinstance(tag_object, Mapping) else None
    tag_type = tag_object.get("type") if isinstance(tag_object, Mapping) else None
    if tag_type != "commit" or tag_sha != expected_sha:
        errors.append(
            f"GitHub tag {TAG} does not resolve to exact release commit {expected_sha}: "
            f"type={tag_type!r}, sha={tag_sha!r}"
        )

    if release_payload.get("tag_name") != TAG:
        errors.append(f"GitHub Release tag is {release_payload.get('tag_name')!r}, expected {TAG!r}")
    if release_payload.get("draft") is not False:
        errors.append("GitHub Release is still a draft")
    if release_payload.get("prerelease") is not False:
        errors.append("GitHub Release is marked as a prerelease")

    assets = release_payload.get("assets")
    asset_names = {
        item.get("name")
        for item in assets
        if isinstance(assets, list) and isinstance(item, Mapping)
    } if isinstance(assets, list) else set()
    missing = EXPECTED_RELEASE_ASSETS - asset_names
    if missing:
        errors.append(f"GitHub Release is missing assets: {sorted(missing)!r}")
    return errors


def _request_json(url: str, *, token: str | None = None, attempts: int = 6) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "SwirEngine-release-verifier"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise RuntimeError(f"Expected JSON object from {url}")
            return data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            if attempt + 1 == attempts:
                raise
            time.sleep(min(2**attempt, 10))
    raise AssertionError("unreachable")


def verify_public_state(*, expected_sha: str = EXPECTED_SOURCE_SHA) -> list[str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    pypi = _request_json(f"https://pypi.org/pypi/swirengine/{VERSION}/json")
    tag = _request_json(
        f"https://api.github.com/repos/Swir/SwirEngine/git/ref/tags/{TAG}", token=token
    )
    release = _request_json(
        f"https://api.github.com/repos/Swir/SwirEngine/releases/tags/{TAG}", token=token
    )
    return validate_pypi_metadata(pypi) + validate_github_state(tag, release, expected_sha)


def verify_public_install() -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--index-url",
            "https://pypi.org/simple",
            f"swirengine=={VERSION}",
        ]
    )
    with tempfile.TemporaryDirectory(prefix="swir-public-2.1-") as temp:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        subprocess.check_call(
            [
                sys.executable,
                "-c",
                "import swirengine; "
                "assert swirengine.__version__ == '2.1.0'; "
                "assert all(hasattr(swirengine, n) for n in ('Game','Scene','Color','Vec3')); "
                "print(swirengine.__version__, swirengine.__file__)",
            ],
            cwd=temp,
            env=env,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify immutable public SwirEngine 2.1.0 publication")
    parser.add_argument("--expected-source", default=EXPECTED_SOURCE_SHA)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    errors = verify_public_state(expected_sha=args.expected_source)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if not args.skip_install:
        verify_public_install()
    print(f"SwirEngine {VERSION} public release verified at {args.expected_source}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
