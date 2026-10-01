"""Built-in restricted SDK adapter for the SwirEditor multiplayer debugger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .editor_extension_sdk22 import (
    EditorExtensionAction22,
    EditorExtensionCapability22,
    EditorExtensionContext22,
    EditorExtensionManifest22,
    EditorExtensionPanel22,
    EditorExtensionRow22,
    EditorExtensionRowTone22,
)
from .editor_multiplayer_debugger22 import EditorMultiplayerDebugger22

MULTIPLAYER_DEBUGGER_EXTENSION_ID_22 = "swir.multiplayer-debugger"
MULTIPLAYER_DEBUGGER_PANEL_ID_22 = "multiplayer-debugger"


class EditorMultiplayerDebuggerExtension22:
    """Publish debugger state through the bounded extension SDK only.

    The adapter receives the transient debugger controller, never an editor app or project
    session. Its no-argument callbacks call only the controller's public API, so the extension
    registry does not pass a raw app, session, root, scene, renderer, or multiplayer session.
    """

    manifest = EditorExtensionManifest22(
        MULTIPLAYER_DEBUGGER_EXTENSION_ID_22,
        "Multiplayer Debugger",
        "2.2",
        (
            EditorExtensionCapability22.PANELS,
            EditorExtensionCapability22.ACTIONS,
        ),
    )

    def __init__(self, controller: EditorMultiplayerDebugger22) -> None:
        if not isinstance(controller, EditorMultiplayerDebugger22):
            raise TypeError("controller must be an EditorMultiplayerDebugger22")
        self._controller = controller
        self._context: EditorExtensionContext22 | None = None
        self._last_capture = "Not exported"

    def on_load(self, context: EditorExtensionContext22) -> None:
        if not isinstance(context, EditorExtensionContext22):
            raise TypeError("context must be an EditorExtensionContext22")
        self._context = context
        self._publish()

    def on_unload(self) -> None:
        self._context = None
        self._controller.close()

    def _refresh(self) -> None:
        # A refresh may follow an out-of-band attach, detach, or runtime replacement.
        # Do not claim that the newly observed diagnostics match an older exported file.
        self._last_capture = "Not exported"
        self._publish()

    def _detach(self) -> None:
        if self._controller.attached:
            self._controller.detach()
        self._last_capture = "Not exported"
        self._publish()

    def _export_capture(self) -> None:
        self._controller.export_capture()
        self._last_capture = "Exported to project diagnostics"
        self._publish()

    def _publish(self) -> None:
        context = self._context
        if context is None:
            return
        if self._controller.closed:
            context.publish_panel(self._closed_panel())
            return
        if not self._controller.attached:
            context.publish_panel(
                self._detached_panel(),
                handlers={"refresh": self._refresh},
            )
            return
        snapshot = self._controller.snapshot()
        context.publish_panel(
            self._attached_panel(snapshot),
            handlers={
                "detach": self._detach,
                "export-capture": self._export_capture,
                "refresh": self._refresh,
            },
        )

    @staticmethod
    def _closed_panel() -> EditorExtensionPanel22:
        return EditorExtensionPanel22(
            MULTIPLAYER_DEBUGGER_PANEL_ID_22,
            "Runtime Diagnostics",
            description="The transient multiplayer debugger is closed.",
            rows=(
                EditorExtensionRow22(
                    "status",
                    "Status",
                    "Closed",
                    EditorExtensionRowTone22.WARNING,
                ),
            ),
        )

    @staticmethod
    def _detached_panel() -> EditorExtensionPanel22:
        return EditorExtensionPanel22(
            MULTIPLAYER_DEBUGGER_PANEL_ID_22,
            "Runtime Diagnostics",
            description=(
                "Attach a production multiplayer runtime through the debugger controller. "
                "Extensions never receive the runtime session object."
            ),
            rows=(
                EditorExtensionRow22(
                    "status",
                    "Status",
                    "Detached",
                    EditorExtensionRowTone22.INFO,
                ),
                EditorExtensionRow22("persistence", "Project save", "Transient; never saved"),
            ),
            actions=(EditorExtensionAction22("refresh", "Refresh"),),
        )

    def _attached_panel(self, snapshot: Mapping[str, Any]) -> EditorExtensionPanel22:
        session = _mapping(snapshot.get("session"))
        peers = _sequence(snapshot.get("peers"))
        events = _sequence(snapshot.get("events"))
        peers_with_round_trip = sum(
            isinstance(peer, Mapping) and isinstance(peer.get("round_trip"), Mapping)
            for peer in peers
        )
        rows = (
            EditorExtensionRow22(
                "status",
                "Status",
                "Attached",
                EditorExtensionRowTone22.GOOD,
            ),
            EditorExtensionRow22("phase", "Session phase", _portable_value(session, "phase")),
            EditorExtensionRow22("peers", "Peers", str(len(peers))),
            EditorExtensionRow22(
                "connected",
                "Connected",
                _portable_value(session, "connected_members"),
            ),
            EditorExtensionRow22(
                "ready",
                "Ready",
                _portable_value(session, "ready_members"),
            ),
            EditorExtensionRow22("events", "Retained events", str(len(events))),
            EditorExtensionRow22(
                "round-trip",
                "RTT sources",
                str(peers_with_round_trip),
            ),
            EditorExtensionRow22("capture", "Capture", self._last_capture),
        )
        return EditorExtensionPanel22(
            MULTIPLAYER_DEBUGGER_PANEL_ID_22,
            "Runtime Diagnostics",
            description=(
                "Privacy-safe aliases and bounded aggregates from the production "
                "multiplayer runtime."
            ),
            rows=rows,
            actions=(
                EditorExtensionAction22("refresh", "Refresh"),
                EditorExtensionAction22("export-capture", "Export capture"),
                EditorExtensionAction22("detach", "Detach"),
            ),
        )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _portable_value(source: Mapping[str, Any], key: str) -> str:
    value = source.get(key)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, str)):
        return str(value)[:512]
    return "Unavailable"


__all__ = [
    "MULTIPLAYER_DEBUGGER_EXTENSION_ID_22",
    "MULTIPLAYER_DEBUGGER_PANEL_ID_22",
    "EditorMultiplayerDebuggerExtension22",
]
