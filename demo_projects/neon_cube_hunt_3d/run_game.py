from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _error_log_path() -> Path:
    return _runtime_root() / "NeonCubeHunt3D-error.log"


def _show_windows_error(message: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Neon Cube Hunt 3D", 0x10)
    except (AttributeError, OSError) as exc:
        # Never let a diagnostic popup hide the original startup failure.
        print(f"Could not show Windows error dialog: {exc}", file=sys.stderr)


def _runtime_probe() -> int:
    """Load the packaged GLFW runtime without opening a window.

    The Windows release workflow runs this from the final PyInstaller executable so a
    missing ``glfw3.dll`` fails CI before the binary is published.
    """

    import glfw

    version = glfw.get_version_string()
    if isinstance(version, bytes):
        version = version.decode("utf-8", errors="replace")
    print(f"GLFW runtime OK: {version}")
    return 0


def run() -> int:
    try:
        if os.environ.get("SWIR_DEMO_RUNTIME_PROBE") == "1":
            return _runtime_probe()

        from neon_cube_hunt.game import main

        main()
        return 0
    except Exception:  # noqa: BLE001 - top-level crash reporter must catch startup failures
        details = traceback.format_exc()
        log_path = _error_log_path()
        try:
            log_path.write_text(details, encoding="utf-8")
        except OSError as exc:
            print(f"Could not write diagnostic log: {exc}", file=sys.stderr)
        print(details, file=sys.stderr)
        _show_windows_error(
            "Neon Cube Hunt 3D could not start.\n\n"
            f"A diagnostic log was written to:\n{log_path}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
