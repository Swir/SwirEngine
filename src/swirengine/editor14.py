"""Supported public surface for the SwirEngine 1.4 editor-authoring milestone.

The rest of SwirEngine keeps its stable 1.x imports. Creator tools that opt into the 1.4 authoring
work can import from this module without depending on private implementation helpers or the internal
layout of the editor-authoring modules.
"""

from .editor_assets import (
    EditorAssetBrowser,
    EditorAssetBrowserFrame,
    EditorAssetDragPayload,
    EditorAssetEntry,
)
from .editor_authoring import (
    EditorAssetPropertyDropResult,
    EditorAuthoringSession,
    EditorAuthoringTransaction,
    EditorBatchPropertyResult,
    EditorMultiGizmoResult,
    EditorSelectionModel,
    EditorSelectionSnapshot,
    SelectionMode,
)
from .editor_authoring_runtime import (
    EditorAuthoringIsolationError,
    EditorAuthoringPlayController,
    EditorAuthoringRuntimeFrame,
)
from .editor_authoring_state import (
    EDITOR_AUTHORING_FORMAT,
    EDITOR_AUTHORING_VERSION,
    EditorAuthoringState,
    capture_editor_authoring,
    restore_editor_authoring,
)
from .editor_authoring_workspace import (
    EditorAuthoringFrontendController,
    EditorAuthoringWorkspace,
)
from .editor_runtime import EditorRuntimeFrame, EditorRuntimeMode, EditorRuntimeSession
from .editor_specialized import (
    EditorSpecializedField,
    EditorSpecializedInspectors,
    EditorSpecializedPropertyResult,
    EditorSpecializedSnapshot,
    SpecializedInspectorKind,
)

__all__ = [
    "EDITOR_AUTHORING_FORMAT",
    "EDITOR_AUTHORING_VERSION",
    "EditorAssetBrowser",
    "EditorAssetBrowserFrame",
    "EditorAssetDragPayload",
    "EditorAssetEntry",
    "EditorAssetPropertyDropResult",
    "EditorAuthoringFrontendController",
    "EditorAuthoringIsolationError",
    "EditorAuthoringPlayController",
    "EditorAuthoringRuntimeFrame",
    "EditorAuthoringSession",
    "EditorAuthoringState",
    "EditorAuthoringTransaction",
    "EditorAuthoringWorkspace",
    "EditorBatchPropertyResult",
    "EditorMultiGizmoResult",
    "EditorRuntimeFrame",
    "EditorRuntimeMode",
    "EditorRuntimeSession",
    "EditorSelectionModel",
    "EditorSelectionSnapshot",
    "EditorSpecializedField",
    "EditorSpecializedInspectors",
    "EditorSpecializedPropertyResult",
    "EditorSpecializedSnapshot",
    "SelectionMode",
    "SpecializedInspectorKind",
    "capture_editor_authoring",
    "restore_editor_authoring",
]
