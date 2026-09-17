from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .development19 import DevelopmentRunner, ProjectRunError, parse_environment_assignments
from .exporting import ExportTarget, NativeBuildError, PackagingProfile, ProjectExporter
from .project19 import ProjectManifest, ProjectManifestError

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


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def new_project(name: str, mode: str) -> Path:
    root = Path(name).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for sub in ("assets", "scenes", "scripts"):
        (root / sub).mkdir()
    template = TEMPLATE_3D if mode == "3d" else TEMPLATE_2D
    (root / "main.py").write_text(template.format(name=name), encoding="utf-8")
    quoted_name = _toml_string(name)
    (root / "swirproject.toml").write_text(
        "\n".join(
            (
                f"name = {quoted_name}",
                f"mode = {_toml_string(mode)}",
                'engine = ">=1.0,<2.0"',
                'entrypoint = "main.py"',
                "",
                "[content]",
                'include = ["assets", "scenes", "scripts"]',
                "",
                "[run]",
                'entrypoint = "main.py"',
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
    (root / ".gitignore").write_text("__pycache__/\n.venv/\nbuild/\ndist/\n", encoding="utf-8")
    return root


def _add_export_parser(subparsers) -> None:
    export = subparsers.add_parser("export")
    export.add_argument("project", nargs="?", default=".")
    export.add_argument("--profile", help="packaging profile from swirproject.toml")
    export.add_argument("--target", choices=tuple(target.value for target in ExportTarget))
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


def _add_run_parser(subparsers) -> None:
    run = subparsers.add_parser("run")
    run.add_argument("project", nargs="?", default=".")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument(
        "--arg",
        action="append",
        default=[],
        help="append one argument to the game process; repeat for multiple arguments",
    )
    run.add_argument(
        "--set-env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="override one environment variable for this development session",
    )
    environment = run.add_mutually_exclusive_group()
    environment.add_argument(
        "--inherit-env",
        dest="inherit_environment",
        action="store_true",
        default=None,
        help="inherit the current host environment",
    )
    environment.add_argument(
        "--clean-env",
        dest="inherit_environment",
        action="store_false",
        help="start the game with only configured environment overrides",
    )


def _profile_from_args(args, project: Path) -> PackagingProfile:
    if args.profile:
        manifest = ProjectManifest.load(project)
        profile = manifest.packaging_profile(args.profile)
        if args.target is not None:
            profile = replace(profile, target=ExportTarget(args.target))
        if args.entrypoint is not None:
            profile = replace(profile, entrypoint=args.entrypoint)
        if args.name is not None:
            profile = replace(profile, app_name=args.name)
        if args.icon is not None:
            profile = replace(profile, icon=args.icon)
        if args.onefile:
            profile = replace(profile, onefile=True)
        if args.windowed:
            profile = replace(profile, console=False)
        return profile
    if args.target is None:
        raise ProjectManifestError("--target is required unless --profile is used")
    return PackagingProfile(
        name=args.name or project.name,
        target=ExportTarget(args.target),
        entrypoint=args.entrypoint or "main.py",
        app_name=args.name,
        icon=args.icon,
        onefile=args.onefile,
        console=not args.windowed,
    )


def _run_doctor(project: str | Path, profile_name: str | None) -> int:
    try:
        manifest = ProjectManifest.load(project)
        diagnostics = manifest.diagnostics(profile_name=profile_name)
    except (FileNotFoundError, ProjectManifestError) as exc:
        print(f"Project check failed: {exc}", file=sys.stderr)
        return 2

    print(f"Project: {manifest.name} ({manifest.mode})")
    print(f"Manifest fingerprint: {manifest.fingerprint}")
    print(f"Development entrypoint: {manifest.run.entrypoint}")
    if profile_name:
        profile = manifest.packaging_profile(profile_name)
        print(f"Packaging profile: {profile.name} -> {profile.target.value}")
    if not diagnostics:
        print("Project manifest OK")
        return 0

    failed = False
    for diagnostic in diagnostics:
        if diagnostic.severity == "error":
            failed = True
        location = f" [{diagnostic.path}]" if diagnostic.path else ""
        print(
            f"{diagnostic.severity.upper()} {diagnostic.code}: "
            f"{diagnostic.message}{location}"
        )
    return 2 if failed else 0


def _run_development_session(args) -> int:
    try:
        project_runner = DevelopmentRunner.load(args.project)
        environment = parse_environment_assignments(args.set_env)
        plan = project_runner.plan(
            extra_arguments=args.arg,
            environment_overrides=environment,
            inherit_environment=args.inherit_environment,
        )
    except (FileNotFoundError, ProjectManifestError, ProjectRunError) as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 2

    command = " ".join(shlex.quote(part) for part in plan.command)
    print(f"Project: {project_runner.manifest.name} ({project_runner.manifest.mode})")
    print(f"Run configuration: {plan.configuration_fingerprint}")
    print(f"Command: {command}")
    if plan.environment_overrides:
        print("Environment overrides: " + ", ".join(sorted(plan.environment_overrides)))
    print(f"Inherit environment: {'yes' if plan.inherit_environment else 'no'}")
    if args.dry_run:
        print("Run plan OK (dry run; game process not started)")
        return 0

    try:
        result = project_runner.execute(plan)
    except OSError as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 2
    return result.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="swirengine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info")
    create = sub.add_parser("new")
    create.add_argument("name")
    create.add_argument("--mode", choices=("2d", "3d"), default="2d")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("project", nargs="?", default=".")
    doctor.add_argument("--profile")
    _add_run_parser(sub)
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
        return _run_doctor(args.project, args.profile)
    if args.command == "run":
        return _run_development_session(args)
    if args.command == "export":
        project = Path(args.project).resolve()
        try:
            profile = _profile_from_args(args, project)
            exporter = ProjectExporter(project)
            if args.build_native:
                build = exporter.build_native(profile, args.output)
                result = build.export
            else:
                build = None
                result = exporter.export(profile, args.output)
        except (FileNotFoundError, NativeBuildError, ProjectManifestError, ValueError) as exc:
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
