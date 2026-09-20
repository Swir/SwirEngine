from __future__ import annotations

from collections.abc import Sequence

from .editor_app21 import EditorProjectOpenError, EditorProjectSession, _build_parser
from .editor_asset_drop21 import TkNativeDropAssetPipelineEditorApp21
from .editor_asset_formats21 import create_format_aware_editor_asset_pipeline21
from .editor_asset_frontend21 import EditorAssetWorkflow21
from .editor_render_backend21 import EditorRenderBackendUnavailable


def run_editor_session21(session: EditorProjectSession) -> None:
    """Run one SwirEditor session with the 2.1 asset workflow attached."""

    if not isinstance(session, EditorProjectSession):
        raise TypeError("session must be an EditorProjectSession")
    backend = create_format_aware_editor_asset_pipeline21(session.asset_browser.manager)
    workflow = EditorAssetWorkflow21(backend, session.asset_browser)
    try:
        try:
            session.enable_live_viewport()
        except EditorRenderBackendUnavailable as exc:
            session.console.write(str(exc), level="warning", source="renderer")
        app = TkNativeDropAssetPipelineEditorApp21(
            session.controller,
            workflow,
            title=f"SwirEditor 2.1 — {session.manifest.name}",
        )
        session._install_file_menu(app)
        session._schedule_recovery(app)
        session.console.write("Asset Pipeline 2.1 attached", source="assets")
        app.run()
    finally:
        workflow.shutdown()
        session.disable_live_viewport()


def main(argv: Sequence[str] | None = None) -> int:
    """SwirEditor 2.1 entry point with the production asset workflow."""

    args = _build_parser().parse_args(None if argv is None else list(argv))
    try:
        session = EditorProjectSession.open(
            args.project,
            scene=args.scene,
            restore_state=not args.fresh_layout,
            restore_recovery=args.recover,
        )
    except (EditorProjectOpenError, ValueError) as exc:
        print(f"SwirEditor failed: {exc}")
        return 2

    if args.headless:
        summary = session.summary()
        print(f"SwirEditor 2.1 project: {summary.project_name} ({summary.mode})")
        print(
            f"Scene: {summary.scene_path} "
            f"({summary.object_count} objects, {summary.entity_count} entities)"
        )
        print(f"Open scenes: {summary.open_scenes}")
        print(f"Assets: {summary.asset_count}")
        print(
            "Persistence: "
            f"scene={'present' if summary.scene_exists else 'new'}, "
            f"state={'present' if summary.editor_state_exists else 'new'}, "
            f"dirty={'yes' if summary.dirty else 'no'}, "
            f"recovery={'yes' if summary.recovery_available else 'no'}"
        )
        return 0

    try:
        run_editor_session21(session)
    except RuntimeError as exc:
        print(f"SwirEditor failed: {exc}")
        return 2
    return 0
