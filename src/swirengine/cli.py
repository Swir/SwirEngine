from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from . import __version__
from .exporting import ExportTarget, NativeBuildError, PackagingProfile, ProjectExporter
from .project import ProjectConfigError, discover_project, load_project_manifest

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
    toml_name = json.dumps(name, ensure_ascii=False)
    (root / "swirproject.toml").write_text(
        "\n".join(
            (
                "schema = 1",
                f"name = {toml_name}",
                f'mode = "{mode}"',
                'engine = ">=1.0,<2.0"',
                'entrypoint = "main.py"',
                "",
                "[paths]",
                'assets = "assets"',
                'scenes = "scenes"',
                'scripts = "scripts"',
                "",
            )
        ),
        encoding="utf-8",
    )
    (root / ".gitignore").write_text("__pycache__/\n.venv/\nbuild/\ndist/\n", encoding="utf-8")
    return root


def _add_export_parser(subparsers) -> None:
    export = subparsers.add_parser("export")
    export.add_argument("project", nargs="?", default=".")
    export.add_argument("--target", choices=tuple(target.value for target in ExportTarget), required=True)
    export.add_argument("--output")
    export.add_argument("--name")
    export.add_argument("--entrypoint")
    export.add_argument("--icon")
    export.add_argument("--onefile", action="store_true")
    export.add_argument("--windowed", action="store_true")
    export.add_argument(
        "--build-native",
        action="store_true",
        help="execute a host-native PyInstaller build after staging (desktop targets only)",
    )


def _project_for_export(project: Path):
    manifest_path = project / "swirproject.toml"
    if not manifest_path.is_file():
        return None
    return load_project_manifest(project)


def _run_doctor(project: str) -> int:
    try:
        manifest = discover_project(project)
    except (FileNotFoundError, ProjectConfigError) as exc:
        print(f"Project doctor failed: {exc}", file=sys.stderr)
        return 2

    print(f"SwirEngine {__version__} project doctor")
    print(f"Project: {manifest.name} | mode={manifest.mode} | schema={manifest.schema}")
    print(f"Root: {manifest.root}")
    failures = 0
    for diagnostic in manifest.diagnostics():
        marker = "OK" if diagnostic.ok else "FAIL"
        print(f"[{marker}] {diagnostic.message}")
        failures += int(not diagnostic.ok)
    if failures:
        print(f"Project status: FAILED ({failures} issue(s))", file=sys.stderr)
        return 2
    print("Project status: OK")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="swirengine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info")
    create = sub.add_parser("new")
    create.add_argument("name")
    create.add_argument("--mode", choices=("2d", "3d"), default="2d")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("project", nargs="?", default=".")
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
    if args.command == "doctor":
        return _run_doctor(args.project)
    if args.command == "export":
        project = Path(args.project).resolve()
        try:
            manifest = _project_for_export(project)
            profile = PackagingProfile(
                name=args.name or (manifest.name if manifest is not None else project.name),
                target=ExportTarget(args.target),
                entrypoint=(
                    args.entrypoint
                    or (manifest.entrypoint.as_posix() if manifest is not None else "main.py")
                ),
                app_name=args.name,
                icon=args.icon,
                onefile=args.onefile,
                console=not args.windowed,
            )
            exporter = ProjectExporter(project)
            if args.build_native:
                build = exporter.build_native(profile, args.output)
                result = build.export
            else:
                build = None
                result = exporter.export(profile, args.output)
        except (FileNotFoundError, NativeBuildError, ProjectConfigError, ValueError) as exc:
            print(f"Export failed: {exc}", file=sys.stderr)
            return 2
        print(f"Exported {profile.target.value}: {result.output_dir}")
        if result.experimental:
            print("Target status: experimental staging export")
        if build is not None:
            print("Native build artifacts:")
            for artifact in build.artifacts:
                print(f"  {artifact}")
        elif result.native_build_command:
            command = " ".join(shlex.quote(part) for part in result.native_build_command)
            print(f"Native build command: {command}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
