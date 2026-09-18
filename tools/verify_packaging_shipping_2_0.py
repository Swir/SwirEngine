from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import venv
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NAME = "swirengine"
EXPECTED_VERSION = "1.5.0"
_MAX_MEMBERS = 50_000
_FORBIDDEN_PARTS = {".git", ".venv", "__pycache__"}


class PackagingShippingError(RuntimeError):
    """Raised when a distribution or clean-install shipping invariant fails."""


@dataclass(frozen=True, slots=True)
class ArtifactSet:
    wheel: Path
    sdist: Path
    wheel_sha256: str
    sdist_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _select_artifacts(dist_dir: Path) -> ArtifactSet:
    root = dist_dir.resolve()
    if not root.is_dir():
        raise PackagingShippingError(f"distribution directory does not exist: {root}")
    wheels = sorted(root.glob("swirengine-*.whl"))
    sdists = sorted(root.glob("swirengine-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise PackagingShippingError(
            "expected exactly one SwirEngine wheel and one sdist; "
            f"found wheels={len(wheels)}, sdists={len(sdists)}"
        )
    return ArtifactSet(
        wheel=wheels[0],
        sdist=sdists[0],
        wheel_sha256=_sha256(wheels[0]),
        sdist_sha256=_sha256(sdists[0]),
    )


def _validate_member_names(names: Iterable[str], *, label: str) -> tuple[str, ...]:
    values = tuple(str(name) for name in names)
    if not values or len(values) > _MAX_MEMBERS:
        raise PackagingShippingError(
            f"{label} must contain 1..{_MAX_MEMBERS} archive members, got {len(values)}"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.replace("\\", "/")
        if not value or "\x00" in value or value.startswith("/"):
            raise PackagingShippingError(f"{label} contains an unsafe member path: {raw!r}")
        path = PurePosixPath(value)
        if any(part in {"", ".", ".."} for part in path.parts):
            raise PackagingShippingError(f"{label} contains path traversal: {raw!r}")
        if any(part.casefold() in _FORBIDDEN_PARTS for part in path.parts):
            raise PackagingShippingError(f"{label} contains forbidden build state: {raw!r}")
        key = value.rstrip("/").casefold()
        if key in seen:
            raise PackagingShippingError(
                f"{label} contains a case-folded duplicate member: {raw!r}"
            )
        seen.add(key)
        normalized.append(value)
    return tuple(normalized)


def _require_metadata(payload: str, *, label: str) -> None:
    fields = {}
    for line in payload.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            fields.setdefault(key, value)
    if fields.get("Name", "").casefold() != EXPECTED_NAME:
        raise PackagingShippingError(f"{label} metadata does not identify {EXPECTED_NAME}")
    if fields.get("Version") != EXPECTED_VERSION:
        raise PackagingShippingError(
            f"{label} version is {fields.get('Version')!r}, expected {EXPECTED_VERSION}"
        )


def _inspect_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = _validate_member_names(archive.namelist(), label="wheel")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise PackagingShippingError(
                f"wheel must contain exactly one METADATA file, found {len(metadata_names)}"
            )
        payload = archive.read(metadata_names[0]).decode("utf-8")
        _require_metadata(payload, label="wheel")
        if not any(name.endswith("swirengine/__init__.py") for name in names):
            raise PackagingShippingError("wheel does not contain swirengine/__init__.py")


def _inspect_sdist(path: Path) -> None:
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = _validate_member_names((member.name for member in members), label="sdist")
        for member in members:
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise PackagingShippingError(
                    f"sdist contains unsupported link/device member: {member.name!r}"
                )
        metadata_names = [name for name in names if name.endswith("/PKG-INFO")]
        if len(metadata_names) != 1:
            raise PackagingShippingError(
                f"sdist must contain exactly one PKG-INFO file, found {len(metadata_names)}"
            )
        metadata = archive.extractfile(metadata_names[0])
        if metadata is None:
            raise PackagingShippingError("sdist PKG-INFO cannot be read")
        _require_metadata(metadata.read().decode("utf-8"), label="sdist")
        if not any(name.endswith("/src/swirengine/__init__.py") for name in names):
            raise PackagingShippingError("sdist does not contain src/swirengine/__init__.py")


def _venv_python(root: Path) -> Path:
    if platform.system() == "Windows":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def _clean_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int = 300,
) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=dict(env),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout)[-5000:]
        raise PackagingShippingError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}"
        )


def _prepare_fixture_copy(root: Path) -> tuple[Path, ...]:
    root.mkdir(parents=True, exist_ok=True)
    fixtures = []
    for relative in (
        Path("examples/2d_game_demo"),
        Path("examples/3d_game_demo"),
        Path("examples/multiplayer_game_demo"),
    ):
        source = ROOT / relative
        if not source.is_dir():
            raise PackagingShippingError(f"maintained fixture is missing: {relative}")
        destination = root / relative.name
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        fixtures.append(destination)
    return tuple(fixtures)


def _assert_isolated_import(python: Path, *, cwd: Path, env: Mapping[str, str]) -> None:
    code = (
        "from pathlib import Path; import sys, swirengine; "
        "package=Path(swirengine.__file__).resolve(); "
        "source=Path(sys.argv[1]).resolve(); "
        "paths=[Path(p).resolve() for p in sys.path if p]; "
        "assert source not in package.parents and package != source, "
        "f'package resolved from source checkout: {package}'; "
        "assert all(p != source and source not in p.parents for p in paths), "
        "f'source checkout leaked into sys.path: {paths}'; "
        f"assert swirengine.__version__ == '{EXPECTED_VERSION}', swirengine.__version__; "
        "print(package)"
    )
    _run([str(python), "-c", code, str(ROOT)], cwd=cwd, env=env)


def _run_fixtures(
    python: Path,
    fixtures: tuple[Path, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> None:
    runtime_env = dict(env)
    runtime_env["SWIR_GAME_DEMO_HEADLESS"] = "1"
    for fixture in fixtures:
        entry = fixture / "run_game.py"
        if not entry.is_file():
            raise PackagingShippingError(f"fixture entrypoint is missing: {entry}")
        _run([str(python), str(entry)], cwd=cwd, env=runtime_env)


def _verify_clean_install(
    artifact: Path,
    *,
    root: Path,
    label: str,
) -> None:
    environment = root / f"{label}-venv"
    work = root / f"{label}-work"
    work.mkdir()
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = _venv_python(environment)
    if not python.is_file():
        raise PackagingShippingError(f"{label} venv interpreter is missing: {python}")
    clean_env = _clean_env()
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            str(artifact),
        ],
        cwd=work,
        env=clean_env,
        timeout=420,
    )
    _assert_isolated_import(python, cwd=work, env=clean_env)
    fixtures = _prepare_fixture_copy(root / f"{label}-fixtures")
    _run_fixtures(python, fixtures, cwd=work, env=clean_env)


def _normalize_expected_system(value: str) -> str:
    return "Darwin" if value == "macOS" else value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify SwirEngine 2.0 wheel/sdist inventories and clean installed "
            "2D/3D/multiplayer runtime outside the development checkout"
        )
    )
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument(
        "--expected-system",
        choices=("Linux", "Windows", "Darwin", "macOS"),
        required=True,
    )
    parser.add_argument("--expected-python", default="3.13")
    args = parser.parse_args()

    expected_system = _normalize_expected_system(args.expected_system)
    if platform.system() != expected_system:
        raise PackagingShippingError(
            f"runner system is {platform.system()}, expected {expected_system}"
        )
    current_python = f"{os.sys.version_info.major}.{os.sys.version_info.minor}"
    if current_python != args.expected_python:
        raise PackagingShippingError(
            f"runner Python is {current_python}, expected {args.expected_python}"
        )

    artifacts = _select_artifacts(args.dist_dir)
    _inspect_wheel(artifacts.wheel)
    _inspect_sdist(artifacts.sdist)

    with tempfile.TemporaryDirectory(prefix="swirengine-2.0-packaging-") as temporary:
        root = Path(temporary)
        _verify_clean_install(artifacts.wheel, root=root, label="wheel")
        _verify_clean_install(artifacts.sdist, root=root, label="sdist")

    print(
        "SwirEngine 2.0 packaging artifact gate OK: "
        f"system={expected_system}, python={current_python}, "
        f"wheel={artifacts.wheel.name}:{artifacts.wheel_sha256}, "
        f"sdist={artifacts.sdist.name}:{artifacts.sdist_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
