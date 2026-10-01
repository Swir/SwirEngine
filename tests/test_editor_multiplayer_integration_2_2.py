from __future__ import annotations

import inspect
from itertools import count
from types import SimpleNamespace

import pytest

from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_asset_app21 import TkIntegratedEditorApp21, run_editor_session21
from swirengine.editor_extension_frontend22 import TkEditorExtensionHostApp22
from swirengine.editor_extension_sdk22 import (
    EditorExtensionCapability22,
    EditorExtensionContext22,
    EditorExtensionManifest22,
    EditorExtensionRegistry22,
)
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_multiplayer_debugger22 import (
    DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22,
    EditorMultiplayerDebugger22,
)
from swirengine.editor_multiplayer_extension22 import (
    MULTIPLAYER_DEBUGGER_EXTENSION_ID_22,
    MULTIPLAYER_DEBUGGER_PANEL_ID_22,
    EditorMultiplayerDebuggerExtension22,
)
from swirengine.editor_ui_designer_frontend22 import TkUIDesignerEditorApp22
from swirengine.multiplayer20 import MultiplayerCompatibility, ProductionMultiplayerSession
from swirengine.project_scaffold21 import new_project21


def _runtime() -> ProductionMultiplayerSession:
    tokens = count()
    compatibility = MultiplayerCompatibility(
        project_id="private-project",
        protocol_version="2.2",
        build_id="private-build",
        replication_schema="private-schema",
        content_fingerprint="private-content",
    )
    runtime = ProductionMultiplayerSession(
        "private-session",
        "private-host",
        compatibility,
        max_members=2,
        token_factory=lambda: f"private-token-{next(tokens):04d}",
    )
    runtime.join("private-peer", compatibility)
    return runtime


def _panel_rows(registry: EditorExtensionRegistry22) -> dict[str, str]:
    snapshot = registry.snapshot()
    extension = next(
        view
        for view in snapshot.extensions
        if view.manifest.extension_id == MULTIPLAYER_DEBUGGER_EXTENSION_ID_22
    )
    panel = next(
        item for item in extension.panels if item.panel_id == MULTIPLAYER_DEBUGGER_PANEL_ID_22
    )
    return {row.row_id: row.value for row in panel.rows}


def test_builtin_adapter_uses_only_restricted_context_and_controller(tmp_path) -> None:
    controller = EditorMultiplayerDebugger22(tmp_path)
    extension = EditorMultiplayerDebuggerExtension22(controller)
    registry = EditorExtensionRegistry22()
    registry.register(extension)

    assert _panel_rows(registry) == {
        "status": "Detached",
        "persistence": "Transient; never saved",
    }
    assert set(inspect.signature(extension._refresh).parameters) == set()
    assert set(inspect.signature(extension._detach).parameters) == set()
    assert set(inspect.signature(extension._export_capture).parameters) == set()
    assert not any(
        name in vars(extension)
        for name in ("app", "session", "root", "scene", "renderer", "plugin_manager")
    )

    controller.attach(_runtime())
    controller.sample("private-host", 7, sent_bytes=64, received_bytes=32)
    refreshed = registry.invoke_action(MULTIPLAYER_DEBUGGER_EXTENSION_ID_22, "refresh")
    assert refreshed.ok
    rows = _panel_rows(registry)
    assert rows["status"] == "Attached"
    assert rows["peers"] == "2"
    assert rows["connected"] == "2"
    assert "private" not in repr(registry.snapshot())

    exported = registry.invoke_action(
        MULTIPLAYER_DEBUGGER_EXTENSION_ID_22,
        "export-capture",
    )
    assert exported.ok
    assert (tmp_path / DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22).is_file()
    assert _panel_rows(registry)["capture"] == "Exported to project diagnostics"

    controller.attach(_runtime())
    refreshed = registry.invoke_action(MULTIPLAYER_DEBUGGER_EXTENSION_ID_22, "refresh")
    assert refreshed.ok
    assert _panel_rows(registry)["capture"] == "Not exported"

    registry.invoke_action(MULTIPLAYER_DEBUGGER_EXTENSION_ID_22, "export-capture")
    assert _panel_rows(registry)["capture"] == "Exported to project diagnostics"
    controller.detach()
    controller.attach(_runtime())
    refreshed = registry.invoke_action(MULTIPLAYER_DEBUGGER_EXTENSION_ID_22, "refresh")
    assert refreshed.ok
    assert _panel_rows(registry)["capture"] == "Not exported"

    detached = registry.invoke_action(MULTIPLAYER_DEBUGGER_EXTENSION_ID_22, "detach")
    assert detached.ok
    assert not controller.attached
    assert _panel_rows(registry)["status"] == "Detached"
    registry.unregister(MULTIPLAYER_DEBUGGER_EXTENSION_ID_22)
    assert controller.closed


def test_integrated_session_owns_transient_tools_without_dirty_or_save(tmp_path) -> None:
    root = new_project21("TransientM9", "2d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    assert isinstance(session.multiplayer_debugger, EditorMultiplayerDebugger22)
    assert isinstance(session.editor_extensions, EditorExtensionRegistry22)
    assert [
        view.manifest.extension_id for view in session.editor_extensions.snapshot().extensions
    ] == [MULTIPLAYER_DEBUGGER_EXTENSION_ID_22]
    session.save()
    assert not session.summary().dirty

    session.multiplayer_debugger.attach(_runtime())
    session.multiplayer_debugger.sample("private-host", 1, sent_bytes=10)
    session.editor_extensions.invoke_action(
        MULTIPLAYER_DEBUGGER_EXTENSION_ID_22,
        "refresh",
    )
    assert session.multiplayer_debugger.attached
    assert not session.multiplayer_debugger.dirty
    assert not session.summary().dirty
    assert not session._all_dirty()

    session.save()
    assert not session.summary().dirty
    assert not (root / DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22).exists()
    reopened = EditorIntegratedProjectSession21.open(root)
    assert not reopened.multiplayer_debugger.attached
    assert not reopened.summary().dirty

    session.close()
    assert session.multiplayer_debugger.closed
    assert session.editor_extensions.snapshot().extensions == ()
    reopened.close()


def test_adopt_installs_fresh_transient_debugger_and_registry(tmp_path) -> None:
    root = new_project21("AdoptM9", "3d", parent=tmp_path)
    base = EditorProjectSession.open(root)
    integrated = EditorIntegratedProjectSession21.adopt(base)

    assert isinstance(integrated.multiplayer_debugger, EditorMultiplayerDebugger22)
    assert isinstance(integrated.editor_extensions, EditorExtensionRegistry22)
    assert not integrated.multiplayer_debugger.attached
    assert not integrated.multiplayer_debugger.closed
    integrated.save()
    assert not integrated.summary().dirty
    integrated.close()


def test_session_close_cleans_every_extension_after_sanitized_unload_failure(tmp_path) -> None:
    root = new_project21("CloseM9", "2d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)

    class FailingExtension:
        manifest = EditorExtensionManifest22(
            "zulu.failure",
            "Failure",
            "1.0",
            (EditorExtensionCapability22.PANELS,),
        )

        @staticmethod
        def on_load(_context: EditorExtensionContext22) -> None:
            return None

        @staticmethod
        def on_unload() -> None:
            raise RuntimeError("private unload failure")

    session.editor_extensions.register(FailingExtension())
    session.console.clear()
    session.close()

    assert session.editor_extensions.snapshot().extensions == ()
    assert session.multiplayer_debugger.closed
    assert session.console.entries[-1].message == "Editor extension shutdown failed."
    assert "private unload" not in repr(session.console.entries)


def test_unified_app_uses_extension_host_as_first_base_and_receives_registry(
    tmp_path,
    monkeypatch,
) -> None:
    assert TkIntegratedEditorApp21.__bases__[0] is TkEditorExtensionHostApp22
    assert issubclass(TkIntegratedEditorApp21, TkUIDesignerEditorApp22)

    root = new_project21("UnifiedM9", "2d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    captured: dict[str, object] = {}
    cleanup: list[str] = []

    def fake_init(_app, _controller, **kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(TkIntegratedEditorApp21, "__init__", fake_init)
    monkeypatch.setattr(TkIntegratedEditorApp21, "run", lambda _app: None)
    monkeypatch.setattr(session, "_install_file_menu", lambda _app: None)
    monkeypatch.setattr(session, "_schedule_recovery", lambda _app: None)
    monkeypatch.setattr(session, "enable_live_viewport", lambda: None)
    monkeypatch.setattr(
        session,
        "disable_live_viewport",
        lambda: cleanup.append("viewport"),
    )
    workflow = SimpleNamespace(shutdown=lambda: cleanup.append("workflow"))
    monkeypatch.setattr(
        "swirengine.editor_asset_app21.create_format_aware_editor_asset_pipeline21",
        lambda _manager: object(),
    )
    monkeypatch.setattr(
        "swirengine.editor_asset_app21.EditorAssetWorkflow21",
        lambda _backend, _browser: workflow,
    )

    run_editor_session21(session)

    assert captured["editor_extensions"] is session.editor_extensions
    assert captured["ui_designer"] is session.ui_designer
    assert cleanup == ["workflow", "viewport"]
    assert session.multiplayer_debugger.closed
    assert session.editor_extensions.snapshot().extensions == ()


def test_early_editor_setup_failure_closes_transient_session(
    tmp_path,
    monkeypatch,
) -> None:
    root = new_project21("EarlyFailureM9", "2d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)

    def fail_pipeline(_manager):
        raise RuntimeError("private early setup failure")

    monkeypatch.setattr(
        "swirengine.editor_asset_app21.create_format_aware_editor_asset_pipeline21",
        fail_pipeline,
    )

    with pytest.raises(RuntimeError, match="private early setup failure"):
        run_editor_session21(session)

    assert session.multiplayer_debugger.closed
    assert session.editor_extensions.snapshot().extensions == ()
