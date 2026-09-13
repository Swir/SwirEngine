from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from . import __version__
from .exporting import ExportTarget, PackagingProfile, ProjectExporter

TEMPLATE_2D = '''from swirengine import Color, Game, Rectangle2D

game = Game("{name}", 1280, 720, mode="2d")
player = game.add(Rectangle2D(0, 0, 140, 80, Color(0.1, 0.7, 1.0, 1.0), name="player"))

@game.update
def update(dt):
    speed = 400
    if game.key("A"):
        player.x -= speed * dt
    if game.key("D"):
        player.x += speed * dt
    if game.key("W"):
        player.y += speed * dt
    if game.key("S"):
        player.y -= speed * dt

game.run()
'''

TEMPLATE_3D = '''from swirengine import Color, Cube3D, Game, Vec3

game = Game("{name}", 1280, 720, mode="3d")
cube = Cube3D(position=Vec3(0, 0, -4), color=Color(0.2, 0.7, 1.0, 1.0))
game.add(cube)

@game.update
def update(dt):
    cube.rotation.y += 50 * dt
    cube.rotation.x += 25 * dt

game.run()
'''


def new_project(name: str, mode: str) -> Path:
    root = Path(name).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for sub in ("assets", "scenes", "scripts"):
        (root / sub).mkdir()
    template = TEMPLATE_3D if mode == "3d" else TEMPLATE_2D
    (root / "main.py").write_text(template.format(name=name), encoding="utf-8")
    (root / "swirproject.toml").write_text(
        f'name = "{name}"\nmode = "{mode}"\nengine = ">=1.0,<2.0"\n', encoding="utf-8"
    )
    (root / ".gitignore").write_text("__pycache__/\n.venv/\nbuild/\ndist/\n", encoding="utf-8")
    return root


def _add_export_parser(subparsers) -> None:
    export = subparsers.add_parser("export")
    export.add_argument("project", nargs="?", default=".")
    export.add_argument("--target", choices=tuple(target.value for target in ExportTarget), required=True)
    export.add_argument("--output")
    export.add_argument("--name")
    export.add_argument("--entrypoint", default="main.py")
    export.add_argument("--icon")
    export.add_argument("--onefile", action="store_true")
    export.add_argument("--windowed", action="store_true")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="swirengine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info")
    create = sub.add_parser("new")
    create.add_argument("name")
    create.add_argument("--mode", choices=("2d", "3d"), default="2d")
    _add_export_parser(sub)
    args = parser.parse_args(argv)

    if args.command == "info":
        print(f"SwirEngine {__version__}")
        print("Backend: ModernGL + GLFW | Modes: 2D, 3D")
        return 0
    if args.command == "new":
        try:
            root = new_project(args.name, args.mode)
        except FileExistsError:
            print(f"Directory already exists: {args.name}", file=sys.stderr)
            return 2
        print(f"Created {args.mode.upper()} project: {root}")
        return 0
    if args.command == "export":
        project = Path(args.project).resolve()
        profile = PackagingProfile(
            name=args.name or project.name,
            target=ExportTarget(args.target),
            entrypoint=args.entrypoint,
            app_name=args.name,
            icon=args.icon,
            onefile=args.onefile,
            console=not args.windowed,
        )
        try:
            result = ProjectExporter(project).export(profile, args.output)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Export failed: {exc}", file=sys.stderr)
            return 2
        print(f"Exported {profile.target.value}: {result.output_dir}")
        if result.experimental:
            print("Target status: experimental staging export")
        if result.native_build_command:
            command = " ".join(shlex.quote(part) for part in result.native_build_command)
            print(f"Native build command: {command}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
