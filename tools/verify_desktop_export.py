from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from swirengine.exporting import ExportTarget, PackagingProfile, ProjectExporter

_TARGET_BY_PLATFORM = {
    "win32": ExportTarget.WINDOWS,
    "linux": ExportTarget.LINUX,
    "darwin": ExportTarget.MACOS,
}


def _native_executable(artifact: Path, app_name: str) -> Path:
    if artifact.is_file():
        return artifact
    suffix = ".exe" if sys.platform == "win32" else ""
    candidate = artifact / f"{app_name}{suffix}"
    if not candidate.is_file():
        raise RuntimeError(f"native executable not found: {candidate}")
    return candidate


def verify(*, onefile: bool = True) -> Path:
    target = _TARGET_BY_PLATFORM.get(sys.platform)
    if target is None:
        raise RuntimeError(f"unsupported desktop verification host: {sys.platform}")

    with tempfile.TemporaryDirectory(prefix="swirengine-export-") as temp:
        root = Path(temp)
        project = root / "project"
        project.mkdir()
        (project / "assets").mkdir()
        (project / "scripts").mkdir()
        (project / "assets" / "marker.txt").write_text("asset-ok", encoding="utf-8")
        (project / "scripts" / "dynamic.py").write_text("DYNAMIC = 'script-ok'\n", encoding="utf-8")
        (project / "main.py").write_text(
            "from pathlib import Path\n"
            "import swirengine\n"
            "root = Path(__file__).resolve().parent\n"
            "asset = (root / 'assets' / 'marker.txt').read_text(encoding='utf-8')\n"
            "script = (root / 'scripts' / 'dynamic.py').read_text(encoding='utf-8')\n"
            "assert \"DYNAMIC = 'script-ok'\" in script\n"
            "print(f'SWIR_DESKTOP_EXPORT_OK:{asset}:{swirengine.__version__}')\n",
            encoding="utf-8",
        )

        app_name = "swir_export_smoke"
        profile = PackagingProfile(
            name=app_name,
            app_name=app_name,
            target=target,
            onefile=onefile,
            console=True,
        )
        result = ProjectExporter(project).build_native(profile, root / "staged")
        if len(result.artifacts) != 1:
            raise RuntimeError(f"expected one top-level native artifact, got {result.artifacts!r}")
        executable = _native_executable(result.artifacts[0], app_name)
        completed = subprocess.run(
            [str(executable)],
            cwd=executable.parent,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "native executable failed "
                f"({completed.returncode}): stdout={completed.stdout!r} stderr={completed.stderr!r}"
            )
        expected_prefix = "SWIR_DESKTOP_EXPORT_OK:asset-ok:"
        if expected_prefix not in completed.stdout:
            raise RuntimeError(f"native smoke marker missing from stdout: {completed.stdout!r}")
        print(completed.stdout.strip())
        return executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onedir", action="store_true", help="verify directory-style output")
    args = parser.parse_args()
    verify(onefile=not args.onedir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
