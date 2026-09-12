## Live visual-editor runtime preview

- added public `EditorViewportImage`, `RendererViewportBridge`, `EditorPreviewFrame` and `EditorPreviewSession`
- `RendererViewportBridge` now renders the active edit/play scene and reads the live RGB framebuffer for editor presentation without adding a mandatory image dependency
- `EditorPreviewSession` keeps the renderer synchronized with `EditorRuntimeSession`, including scene switches while in Edit mode
- `TkEditorApp` now exposes Play/Pause, Stop and single-frame Step controls and embeds live renderer frames directly in the Viewport panel
- runtime ticking remains isolated from authoring state, while Stop returns the editor to the unchanged edit scene
- added regression coverage for framebuffer orientation/validation, Play/Pause/Step/Stop behavior and workspace scene switching
