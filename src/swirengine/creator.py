"""Creator/editor integration helpers for SwirEngine 1.3.

This additive namespace keeps the stable top-level 1.x API uncluttered while providing one obvious
import surface for toolkit-neutral editor-system diagnostics.
"""

from .editor_systems import (
    CreatorEditorFrame,
    CreatorEditorIntegration,
    EditorSystemFrame,
    EditorSystemMetric,
    EditorSystemRegistry,
    EditorSystemSnapshot,
)

__all__ = [
    "CreatorEditorFrame",
    "CreatorEditorIntegration",
    "EditorSystemFrame",
    "EditorSystemMetric",
    "EditorSystemRegistry",
    "EditorSystemSnapshot",
]
