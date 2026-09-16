"""SwirEngine 1.5 Project System 2.0 deterministic integration demo.

Run from the repository root:
    python examples/demo_project_system_1_5.py
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.project import discover_project, load_project_manifest


def main() -> int:
    with TemporaryDirectory(prefix="swirengine-project15-") as temporary:
        root = Path(temporary) / "DemoProject"
        (root / "assets").mkdir(parents=True)
        (root / "worlds").mkdir()
        (root / "scripts" / "gameplay").mkdir(parents=True)
        (root / "scripts" / "start.py").write_text("print('boot')\n", encoding="utf-8")
        (root / "swirproject.toml").write_text(
            "\n".join(
                (
                    "schema = 1",
                    'name = "Project System Demo"',
                    'mode = "3d"',
                    'engine = ">=1.0,<2.0"',
                    'entrypoint = "scripts/start.py"',
                    "",
                    "[paths]",
                    'assets = "assets"',
                    'scenes = "worlds"',
                    'scripts = "scripts"',
                    "",
                )
            ),
            encoding="utf-8",
        )

        project = load_project_manifest(root)
        discovered = discover_project(root / "scripts" / "gameplay")
        if project != discovered:
            raise AssertionError("project discovery did not resolve the loaded project")
        if not project.layout_ok:
            raise AssertionError(f"generated project layout is incomplete: {project.diagnostics()}")
        if project.entrypoint.as_posix() != "scripts/start.py":
            raise AssertionError("project entrypoint was not normalized")

        print(
            "SwirEngine Project System 2.0 OK: "
            f"name={project.name!r}, mode={project.mode}, schema={project.schema}, "
            f"entrypoint={project.entrypoint.as_posix()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
