from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .creator_workflow20 import CreatorProjectWorkflow
from .exporting import ExportTarget, NativeBuildError, PackagingProfile, ProjectExporter
from .project19 import ProjectManifest, ProjectManifestError
from .run_sessions19 import RunSessionError, create_run_plan, execute_run_plan
from .shipping19 import ProjectShippingDefaults, ShippingContractError

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
    for sub in ("assets", "scenes", "prefabs", "scripts", "settings"):
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
    run = subparsers.add_parser(
        "run",
        help="start a manifest-driven development session",
    )
    run.add_argument("project", nargs="?", default=".")
    run.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="override one child-process environment variable; repeatable",
    )
    run.add_argument(
        "--clean-env",
        action="store_true",
        help="do not inherit the parent process environment",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the deterministic run plan without starting the game",
    )
    run.add_argument(
        "game_args",
        nargs="*",
        help="plain positional arguments forwarded to the game entrypoint",
    )


def _add_workflow_parser(subparsers) -> None:
    workflow = subparsers.add_parser(
        "workflow",
        help="inspect the integrated creator/run/settings/scenes/content/export project contract",
    )
    workflow.add_argument("project", nargs="?", default=".")
    workflow.add_argument("--profile", help="validate one packaging profile")
    workflow.add_argument(
        "--prepare",
        action="store_true",
        help="create missing creator directories and editable input/settings defaults",
    )
    workflow.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="emit a machine-readable project workflow report",
    )
    workflow.add_argument(
        "--skip-document-validation",
        action="store_true",
        help="skip decoding declared scene/prefab documents while keeping path/graph checks",
    )


def _split_run_forwarded_args(argv) -> tuple[list[str], tuple[str, ...]]:
    """Split the run-command ``--`` boundary before argparse sees it.

    Python 3.10 and newer argparse releases differ when a subparser combines optional
    arguments with a trailing ``nargs='*'`` positional. Handling the conventional ``--``
    separator here gives every supported Python version the same creator-facing contract
    and leaves every other SwirEngine command untouched.
    """

    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] != "run":
        return values, ()
    try:
        boundary = values.index("--")
    except ValueError:
        return values, ()
    return values[:boundary], tuple(values[boundary + 1 :])


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


def _print_diagnostic(diagnostic, *, stream=None) -> None:
    location = f" [{diagnostic.path}]" if diagnostic.path else ""
    print(
        f"{diagnostic.severity.upper()} {diagnostic.code}: "
        f"{diagnostic.message}{location}",
        file=stream,
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
        _print_diagnostic(diagnostic)
    return 2 if failed else 0


def _run_workflow(args) -> int:
    workflow = CreatorProjectWorkflow(args.project)
    if args.prepare:
        try:
            workflow.prepare()
        except (OSError, ValueError, ShippingContractError) as exc:
            print(f"Workflow preparation failed: {exc}", file=sys.stderr)
            return 2

    report = workflow.inspect(
        profile_name=args.profile,
        validate_documents=not args.skip_document_validation,
    )
    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0 if report.ready else 2

    mode = report.mode or "unknown"
    status = "READY" if report.ready else "BLOCKED"
    print(f"Creator workflow: {report.name} ({mode}) -> {status}")
    print(f"Workflow fingerprint: {report.fingerprint}")
    print(f"Profiles: {', '.join(report.profiles) if report.profiles else '<none>'}")
    if report.selected_profile:
        print(f"Selected profile: {report.selected_profile}")
    print(f"Scene packages: {report.scene_packages}")
    print(f"Content build nodes: {report.content_nodes}")
    print(
        "Editable defaults: "
        f"input={'yes' if report.input_defaults_present else 'fallback'}, "
        f"settings={'yes' if report.settings_defaults_present else 'fallback'}"
    )
    if report.user_data_platform and report.user_data_source:
        print(f"Save/profile policy: {report.user_data_platform} via {report.user_data_source}")
    if not report.diagnostics:
        print("Creator workflow OK")
    for diagnostic in report.diagnostics:
        _print_diagnostic(
            diagnostic,
            stream=sys.stderr if diagnostic.severity == "error" else None,
        )
        if diagnostic.action:
            print(f"  Action: {diagnostic.action}")
    return 0 if report.ready else 2


def _run_project(args) -> int:
    try:
        manifest = ProjectManifest.load(args.project)
        diagnostics = manifest.run_diagnostics()
        errors = [item for item in diagnostics if item.severity == "error"]
        for diagnostic in diagnostics:
            _print_diagnostic(
                diagnostic,
                stream=sys.stderr if diagnostic.severity == "error" else None,
            )
        if errors:
            return 2

        forwarded = tuple(args.game_args)
        plan = create_run_plan(
            manifest,
            forwarded_args=forwarded,
            environment_overrides=args.env,
            clean_environment=args.clean_env,
        )
    except (FileNotFoundError, ProjectManifestError, RunSessionError) as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 2

    print(f"Development session: {manifest.name} ({manifest.mode})")
    print(f"Run plan fingerprint: {plan.fingerprint}")
    print(f"Working directory: {plan.working_directory}")
    print(f"Command: {shlex.join(plan.command)}")
    print(
        "Environment: "
        + ("inherit + declared overrides" if plan.inherit_environment else "declared variables only")
    )
    if args.dry_run:
        print("Dry run: game process was not started")
        return 0

    try:
        return_code = execute_run_plan(plan)
    except RunSessionError as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Development session interrupted", file=sys.stderr)
        return 130

    if return_code:
        print(f"Game exited with code {return_code}", file=sys.stderr)
    return return_code


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
    _add_workflow_parser(sub)
    _add_run_parser(sub)
    _add_export_parser(sub)
    parse_argv, separator_args = _split_run_forwarded_args(argv)
    args = parser.parse_args(parse_argv)
    if args.command == "run" and separator_args:
        args.game_args.extend(separator_args)

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
    if args.command == "workflow":
        return _run_workflow(args)
    if args.command == "run":
        return _run_project(args)
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
