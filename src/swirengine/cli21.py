from __future__ import annotations

import argparse
import sys

from . import cli as legacy_cli
from .editor_app21 import DEFAULT_EDITOR_SCENE
from .project_scaffold21 import new_project21


def _new_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swirengine new")
    parser.add_argument("name")
    parser.add_argument("--mode", choices=("2d", "3d"), default="2d")
    return parser


def _editor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swirengine editor")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--scene", default=DEFAULT_EDITOR_SCENE)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--fresh-layout", action="store_true")
    parser.add_argument("--recover", action="store_true")
    return parser


def _run_new(argv: list[str]) -> int:
    args = _new_parser().parse_args(argv)
    try:
        root = new_project21(args.name, args.mode)
    except FileExistsError:
        print(f"Directory already exists: {args.name}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"Project creation failed: {exc}", file=sys.stderr)
        return 2
    print(f"Created {args.mode.upper()} project: {root}")
    return 0


def _run_editor(argv: list[str]) -> int:
    from .editor_asset_app21 import main as editor_main
    from .editor_asset_app21 import run_editor_session21

    args = _editor_parser().parse_args(argv)
    if args.project is None and not args.headless and not args.recover:
        try:
            from .project_hub21 import TkProjectHubApp

            session = TkProjectHubApp().choose()
        except RuntimeError as exc:
            print(f"SwirEditor failed: {exc}")
            return 2
        if session is None:
            return 0
        try:
            run_editor_session21(session)
        except RuntimeError as exc:
            print(f"SwirEditor failed: {exc}")
            return 2
        return 0

    forwarded: list[str] = ["." if args.project is None else args.project]
    if args.scene != DEFAULT_EDITOR_SCENE:
        forwarded.extend(("--scene", args.scene))
    if args.headless:
        forwarded.append("--headless")
    if args.fresh_layout:
        forwarded.append("--fresh-layout")
    if args.recover:
        forwarded.append("--recover")
    return editor_main(forwarded)


def editor_entry(argv: list[str] | None = None) -> int:
    """Standalone SwirEditor entry point sharing the Project Hub and editor router."""

    values = list(sys.argv[1:] if argv is None else argv)
    return _run_editor(values)


def main(argv: list[str] | None = None) -> int:
    """2.1 command router preserving every established 2.0 command by delegation."""

    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "editor":
        return _run_editor(values[1:])
    if values and values[0] == "new":
        return _run_new(values[1:])
    return legacy_cli.main(values)


if __name__ == "__main__":
    raise SystemExit(main())
