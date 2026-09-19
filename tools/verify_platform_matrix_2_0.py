from __future__ import annotations

import argparse
import importlib
import json
import platform
import re
import struct
import sys
from importlib.metadata import metadata, version
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_SYSTEMS = frozenset({"Linux", "Windows", "Darwin"})
SUPPORTED_PYTHONS = frozenset({"3.10", "3.11", "3.12", "3.13", "3.14"})
BASE_RUNTIME_MODULES = ("numpy", "moderngl", "glfw", "PIL", "typing_extensions")
_SYSTEM_ALIASES = {"macOS": "Darwin"}
_WINDOWS_X64_MACHINES = frozenset({"AMD64", "x86_64"})


def _requires_python() -> frozenset[str]:
    value = metadata("swirengine")["Requires-Python"]
    if value is None:
        raise RuntimeError("installed swirengine metadata has no Requires-Python")
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def _module_path(module_name: str) -> str:
    module = importlib.import_module(module_name)
    file_name = getattr(module, "__file__", None)
    return "<built-in>" if file_name is None else str(Path(file_name).resolve())


def _candidate_version(root: Path = ROOT) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    project_version = str(project["version"])
    roadmap = (root / "ROADMAP_2_0.md").read_text(encoding="utf-8")
    final_checked = bool(
        re.search(
            r"^- \[x\] \*\*10\. SwirEngine 2\.0 Final Release Gate & Public Verification\*\*",
            roadmap,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    )
    final_open = bool(
        re.search(
            r"^- \[ \] \*\*10\. SwirEngine 2\.0 Final Release Gate & Public Verification\*\*",
            roadmap,
            flags=re.MULTILINE,
        )
    )
    if final_checked == final_open:
        raise RuntimeError("Milestone 10 must appear exactly once as checked or unchecked")
    expected = "2.0.0" if final_checked else "1.5.0"
    if project_version != expected:
        raise RuntimeError(
            "project version disagrees with Milestone 10 release phase: "
            f"expected {expected}, found {project_version}"
        )
    return expected


def verify(
    *,
    expected_system: str | None = None,
    expected_python: str | None = None,
    require_vendored_native: bool = False,
) -> dict[str, object]:
    system = platform.system()
    machine = platform.machine() or "unknown"
    python_implementation = platform.python_implementation()
    python_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    pointer_bits = struct.calcsize("P") * 8
    normalized_expected_system = (
        None if expected_system is None else _SYSTEM_ALIASES.get(expected_system, expected_system)
    )

    if python_implementation != "CPython":
        raise RuntimeError(
            "SwirEngine 2.0 support matrix currently verifies CPython only, "
            f"found {python_implementation}"
        )
    if system not in SUPPORTED_SYSTEMS:
        raise RuntimeError(f"unsupported operating-system family for 2.0 matrix: {system}")
    if python_minor not in SUPPORTED_PYTHONS:
        raise RuntimeError(f"unsupported CPython minor for 2.0 matrix: {python_minor}")
    if pointer_bits != 64:
        raise RuntimeError(f"2.0 matrix requires a 64-bit interpreter, found {pointer_bits}-bit")
    if normalized_expected_system is not None and system != normalized_expected_system:
        raise RuntimeError(f"expected system {normalized_expected_system}, found {system}")
    if expected_python is not None and python_minor != expected_python:
        raise RuntimeError(f"expected Python {expected_python}, found {python_minor}")
    if require_vendored_native and (
        system != "Windows" or python_minor != "3.14" or machine not in _WINDOWS_X64_MACHINES
    ):
        raise RuntimeError(
            "vendored native renderer verification is restricted to "
            "Windows x86-64 on CPython 3.14"
        )

    expected_package_version = _candidate_version()
    package_version = version("swirengine")
    if package_version != expected_package_version:
        raise RuntimeError(
            "installed package version disagrees with the active 2.0 release phase: "
            f"expected {expected_package_version}, found {package_version}"
        )
    requires_python = _requires_python()
    if requires_python != frozenset({">=3.10", "<3.15"}):
        raise RuntimeError(f"unexpected Requires-Python contract: {sorted(requires_python)}")

    swirengine = importlib.import_module("swirengine")
    if getattr(swirengine, "__version__", None) != package_version:
        raise RuntimeError("swirengine.__version__ disagrees with installed package metadata")
    for name in ("Game", "Color", "Vec3"):
        if not hasattr(swirengine, name):
            raise RuntimeError(f"required public runtime export is missing: {name}")

    module_paths = {name: _module_path(name) for name in BASE_RUNTIME_MODULES}
    module_paths["glcontext"] = _module_path("glcontext")
    if require_vendored_native:
        for module_name in ("moderngl", "glcontext"):
            if "_vendor_native" not in module_paths[module_name]:
                raise RuntimeError(
                    f"{module_name} is not loaded from the vendored Windows CPython 3.14 payload: "
                    f"{module_paths[module_name]}"
                )

    result: dict[str, object] = {
        "system": system,
        "machine": machine,
        "pointer_bits": pointer_bits,
        "python_implementation": python_implementation,
        "python": python_minor,
        "package_version": package_version,
        "requires_python": sorted(requires_python),
        "vendored_native_required": require_vendored_native,
        "modules": module_paths,
    }
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the SwirEngine 2.0 OS/Python runtime cell")
    parser.add_argument(
        "--expected-system",
        choices=sorted(SUPPORTED_SYSTEMS | frozenset(_SYSTEM_ALIASES)),
    )
    parser.add_argument("--expected-python", choices=sorted(SUPPORTED_PYTHONS))
    parser.add_argument("--require-vendored-native", action="store_true")
    args = parser.parse_args()
    verify(
        expected_system=args.expected_system,
        expected_python=args.expected_python,
        require_vendored_native=args.require_vendored_native,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
