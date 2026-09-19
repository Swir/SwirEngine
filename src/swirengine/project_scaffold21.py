from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from .cli import TEMPLATE_2D, TEMPLATE_3D
from .shipping19 import ProjectShippingDefaults

ENGINE_REQUIREMENT_2_1 = ">=2.0,<3.0"


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _child_project_root(name: str, parent: str | Path | None) -> tuple[Path, str]:
    raw = str(name).strip()
    if not raw:
        raise ValueError("project name cannot be empty")
    if parent is None:
        return Path(raw).expanduser().resolve(), raw

    posix = PurePosixPath(raw.replace("\\", "/"))
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
        or len(posix.parts) != 1
    ):
        raise ValueError("Project Hub names must be a single directory name")
    base = Path(parent).expanduser().resolve()
    return (base / raw).resolve(), raw


def new_project21(
    name: str,
    mode: str,
    *,
    parent: str | Path | None = None,
) -> Path:
    """Create a SwirEngine 2.x project without changing the published 2.0 package version.

    This is the 2.1 creator-facing scaffold used by the unified command wrapper and Project Hub.
    The legacy :mod:`swirengine.cli` helper remains untouched as a compatibility surface while the
    new workflow can correctly declare compatibility with the already-published 2.x line.
    """

    if mode not in {"2d", "3d"}:
        raise ValueError("mode must be '2d' or '3d'")
    root, project_name = _child_project_root(name, parent)
    root.mkdir(parents=True, exist_ok=False)
    for sub in ("assets", "scenes", "prefabs", "scripts", "settings"):
        (root / sub).mkdir()

    template = TEMPLATE_3D if mode == "3d" else TEMPLATE_2D
    (root / "main.py").write_text(template.format(name=project_name), encoding="utf-8")
    quoted_name = _toml_string(project_name)
    (root / "swirproject.toml").write_text(
        "\n".join(
            (
                f"name = {quoted_name}",
                f"mode = {_toml_string(mode)}",
                f"engine = {_toml_string(ENGINE_REQUIREMENT_2_1)}",
                'entrypoint = "main.py"',
                "",
                "[content]",
                'include = ["assets", "scenes", "prefabs", "scripts", "config"]',
                "",
                "[run]",
                'entrypoint = "main.py"',
                'working_directory = "."',
                "arguments = []",
                "inherit_environment = true",
                "",
                "[profiles.windows]",
                'target = "windows"',
                f"app_name = {quoted_name}",
                "onefile = false",
                "console = true",
                "",
                "[profiles.linux]",
                'target = "linux"',
                f"app_name = {quoted_name}",
                "onefile = false",
                "console = true",
                "",
                "[profiles.macos]",
                'target = "macos"',
                f"app_name = {quoted_name}",
                "onefile = false",
                "console = true",
                "",
            )
        ),
        encoding="utf-8",
    )
    ProjectShippingDefaults.load(root).write_templates()
    (root / ".gitignore").write_text("__pycache__/\n.venv/\nbuild/\ndist/\n", encoding="utf-8")
    return root
