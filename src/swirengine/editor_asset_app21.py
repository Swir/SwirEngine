from __future__ import annotations

from collections.abc import Sequence

from .editor_app21 import EditorProjectOpenError, EditorProjectSession, _build_parser
from .editor_asset_drop21 import TkNativeDropAssetPipelineEditorApp21
from .editor_asset_formats21 import create_format_aware_editor_asset_pipeline21
from .editor_asset_frontend21 import EditorAssetWorkflow21
from .editor_audio_frontend21 import TkAudioEditorApp21
from .editor_integrated_session21 import EditorIntegratedProjectSession21
from .editor_render_backend21 import EditorRenderBackendUnavailable


class TkIntegratedEditorApp21(TkAudioEditorApp21, TkNativeDropAssetPipelineEditorApp21):
    """Unified SwirEditor shell for gameplay creator tools and the production asset pipeline."""


def run_editor_session21(session: EditorProjectSession) -> None:
    """Run one fully integrated SwirEditor 2.1 creator session."""

    session = EditorIntegratedProjectSession21.adopt(session)
    backend = create_format_aware_editor_asset_pipeline21(session.asset_browser.manager)
    workflow = EditorAssetWorkflow21(backend, session.asset_browser)
    try:
        try:
            session.enable_live_viewport()
        except EditorRenderBackendUnavailable as exc:
            session.console.write(str(exc), level="warning", source="renderer")
        app = TkIntegratedEditorApp21(
            session.controller,
            asset_workflow=workflow,
            project_root=session.manifest.root,
            gameplay=session.gameplay,
            animation=session.animation,
            physics=session.physics,
            navigation=session.navigation,
            audio=session.audio,
            title=f"SwirEditor 2.1 — {session.manifest.name}",
        )
        session._install_file_menu(app)
        session._schedule_recovery(app)
        session.console.write("Asset Pipeline 2.1 attached", source="assets")
        session.console.write("Audio creator tooling attached", source="audio")
        app.run()
    finally:
        workflow.shutdown()
        session.disable_live_viewport()


def main(argv: Sequence[str] | None = None) -> int:
    """SwirEditor 2.1 entry point with the integrated production creator workflow."""

    args = _build_parser().parse_args(None if argv is None else list(argv))
    try:
        session = EditorIntegratedProjectSession21.open(
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