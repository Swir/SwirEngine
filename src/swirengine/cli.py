from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__

TEMPLATE_2D = '''from swirengine import Game, Rectangle2D, Color

game = Game("{name}", 1280, 720, mode="2d")
player = Rectangle2D(0, 0, 140, 80, Color(0.1, 0.7, 1.0, 1.0))
game.scene.add(player)

@game.update
def update(dt):
    speed = 400
    if game.input.key("A"):
        player.x -= speed * dt
    if game.input.key("D"):
        player.x += speed * dt
    if game.input.key("W"):
        player.y += speed * dt
    if game.input.key("S"):
        player.y -= speed * dt

game.run()
'''

TEMPLATE_3D = '''from swirengine import Game, Cube3D, Color, Vec3

game = Game("{name}", 1280, 720, mode="3d")
cube = Cube3D(position=Vec3(0, 0, -4), color=Color(0.2, 0.7, 1.0, 1.0))
game.scene.add(cube)

@game.update
def update(dt):
    cube.rotation.y += 50 * dt
    cube.rotation.x += 25 * dt

game.run()
'''


def new_project(name: str, mode: str) -> Path:
    root = Path(name).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for folder in ("assets", "scenes", "scripts"):
        (root / folder).mkdir()
    template = TEMPLATE_3D if mode == "3d" else TEMPLATE_2D
    (root / "main.py").write_text(template.format(name=name), encoding="utf-8")
    (root / "swirproject.toml").write_text(f'name = "{name}"\nmode = "{mode}"\nengine = ">=0.1,<0.2"\n', encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n.venv/\n", encoding="utf-8")
    return root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="swirengine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info")
    create = sub.add_parser("new")
    create.add_argument("name")
    create.add_argument("--mode", choices=("2d", "3d"), default="2d")
    args = parser.parse_args(argv)
    if args.command == "info":
        print(f"SwirEngine {__version__}")
        print("Backend: ModernGL + GLFW")
        print("Modes: 2D, 3D")
        return 0
    if args.command == "new":
        try:
            root = new_project(args.name, args.mode)
        except FileExistsError:
            print(f"Directory already exists: {args.name}", file=sys.stderr)
            return 2
        print(f"Created {args.mode.upper()} project: {root}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
