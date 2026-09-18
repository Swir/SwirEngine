from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import venv


_PROBE = r'''
from __future__ import annotations

import sys
from pathlib import Path

from swirengine.desktop_shipping19 import build_desktop_shipping, verify_desktop_shipping
from swirengine.project19 import ProjectManifest

root = Path(sys.argv[1]).resolve()
target = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
(root / "main.py").write_text("print('SWIR_DESKTOP_SHIPPING_PROBE_OK')\n", encoding="utf-8")
manifest_text = (
    'name = "Clean Shipping Probe"\n'
    'mode = "2d"\n'
    'entrypoint = "main.py"\n'
    '\n'
    '[content]\n'
    'include = []\n'
    '\n'
    '[profiles.native]\n'
    f'target = "{target}"\n'
    'app_name = "CleanShip"\n'
    'include = []\n'
    'onefile = true\n'
    'console = true\n'
)
(root / "swirproject.toml").write_text(manifest_text, encoding="utf-8")
manifest = ProjectManifest.load(root)
result = build_desktop_shipping(manifest, "native", root.parent / "ship")
verify_desktop_shipping(result.manifest_path, plan_path=result.plan_path)
print(result.plan.fingerprint)
print(result.manifest.fingerprint)
'''


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def _find_wheel(wheelhouse: Path) -> Path:
    wheels = sorted(wheelhouse.glob("swirengine-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(
            f"expected exactly one SwirEngine wheel in {wheelhouse}, found {len(wheels)}"
        )
    return wheels[0].resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a clean wheel install and host-native SwirEngine 1.9 shipping build"
    )
    parser.add_argument("--wheelhouse", type=Path, default=Path("wheelhouse"))
    args = parser.parse_args()
    wheel = _find_wheel(args.wheelhouse)

    with tempfile.TemporaryDirectory(prefix="swir-clean-shipping-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        project = root / "project"
        project.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _venv_python(environment)
        if not python.is_file():
            raise SystemExit(f"clean environment Python was not created: {python}")

        install = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(wheel),
                "pyinstaller",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
        if install.returncode:
            raise SystemExit(
                "clean wheel install failed:\n"
                + (install.stderr[-4000:] or install.stdout[-4000:])
            )

        probe = subprocess.run(
            [str(python), "-c", _PROBE, str(project)],
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
        if probe.returncode:
            raise SystemExit(
                "clean desktop shipping probe failed:\n"
                + (probe.stderr[-4000:] or probe.stdout[-4000:])
            )

        executable = root / "ship" / "native-dist" / (
            "CleanShip.exe" if os.name == "nt" else "CleanShip"
        )
        if not executable.is_file():
            raise SystemExit(
                f"native shipping probe did not create expected executable: {executable}"
            )
        runtime = subprocess.run(
            [str(executable)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if runtime.returncode:
            raise SystemExit(
                f"packaged probe exited with {runtime.returncode}:\n"
                + (runtime.stderr[-4000:] or runtime.stdout[-4000:])
            )
        if "SWIR_DESKTOP_SHIPPING_PROBE_OK" not in runtime.stdout:
            raise SystemExit("packaged probe did not emit the expected runtime marker")
        print("clean desktop shipping wheel/build/runtime probe: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
