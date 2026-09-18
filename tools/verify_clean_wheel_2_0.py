from __future__ import annotations

import argparse
import os
import platform
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _venv_python(root: Path) -> Path:
    if platform.system() == "Windows":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> None:
    subprocess.run(command, check=True, env=env, cwd=cwd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Install a SwirEngine wheel into a clean venv and run "
            "2.0 platform/runtime probes"
        )
    )
    parser.add_argument(
        "--expected-system",
        choices=("Linux", "Windows", "Darwin", "macOS"),
        required=True,
    )
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument(
        "--expected-python",
        choices=("3.10", "3.11", "3.12", "3.13", "3.14"),
        required=True,
    )
    parser.add_argument("--require-vendored-native", action="store_true")
    args = parser.parse_args()

    wheel_dir = args.wheel_dir.resolve()
    wheels = sorted(wheel_dir.glob("swirengine-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(
            f"expected exactly one SwirEngine wheel in {wheel_dir}, found {len(wheels)}"
        )
    wheel = wheels[0]

    with tempfile.TemporaryDirectory(prefix="swirengine-2.0-clean-") as temporary:
        env_root = Path(temporary)
        venv.EnvBuilder(with_pip=True, clear=True).create(env_root)
        python = _venv_python(env_root)
        if not python.is_file():
            raise RuntimeError(f"clean-environment interpreter was not created: {python}")

        clean_env = _clean_env()
        _run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", str(wheel)],
            env=clean_env,
            cwd=env_root,
        )

        import_guard = (
            "from pathlib import Path; import sys, swirengine; "
            "package=Path(swirengine.__file__).resolve(); source=Path(sys.argv[1]).resolve(); "
            "assert source not in package.parents, "
            "f'clean wheel resolved from source checkout: {package}'; print(package)"
        )
        _run(
            [str(python), "-c", import_guard, str(ROOT)],
            env=clean_env,
            cwd=env_root,
        )

        probe = [
            str(python),
            str(ROOT / "tools" / "verify_platform_matrix_2_0.py"),
            "--expected-system",
            args.expected_system,
            "--expected-python",
            args.expected_python,
        ]
        if args.require_vendored_native:
            probe.append("--require-vendored-native")
        _run(probe, env=clean_env, cwd=env_root)

        runtime_env = dict(clean_env)
        runtime_env["SWIR_GAME_DEMO_HEADLESS"] = "1"
        _run(
            [str(python), str(ROOT / "examples" / "2d_game_demo" / "run_game.py")],
            env=runtime_env,
            cwd=env_root,
        )
        _run(
            [str(python), str(ROOT / "examples" / "3d_game_demo" / "run_game.py")],
            env=runtime_env,
            cwd=env_root,
        )

    print(
        "SwirEngine 2.0 clean-wheel platform gate OK: "
        f"wheel={wheel.name}, system={args.expected_system}, python={args.expected_python}, "
        f"vendored_native={args.require_vendored_native}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
