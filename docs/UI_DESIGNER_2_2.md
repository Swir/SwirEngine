# UI Designer 2.0 - SwirEngine 2.2 M8

This document describes the Milestone 8 source-development contract. It does not mark M8 accepted
and does not publish SwirEngine 2.2. The verified roadmap remains 7/10 until the exact implementation
head and the later merged `main` head complete their required gates.

## Portable authoring document

`EditorUIDesignerTooling22` owns the deterministic `config/ui-designer.json` document. Its format is
`swirengine.ui-designer`, version 1. The document stores only portable data:

- a reference canvas and bounded responsive scale limits;
- retained widgets with stable ids, parent/order relationships, flow or viewport-relative anchors,
  size, offsets, visibility, enabled/focusable state and optional action labels;
- a complete project theme plus reusable named style overrides;
- deterministic UI animation clips, tracks and keyframes.

Action labels are data, not executable code. A shipping application supplies a handler mapping when
building the runtime. A declared action without a handler fails closed. Editor previews install
inert handlers, so focus and activation can be inspected without running project callbacks.

The earlier `config/ui-hud.json` and `EditorUIHudTooling21` contract remain available unchanged for
2.1 projects. UI Designer 2.0 is additive and does not silently rewrite or reinterpret that file.

## Shipping runtime

The designer builds the production `UIToolkit` retained tree and uses its existing `UIManager`
controls. Top-level anchors resolve against the viewport; nested anchors resolve against the parent
rectangle. Widgets without an anchor remain in deterministic container flow. The shipping toolkit is
still the only keyboard, pointer and gamepad focus/navigation implementation.

Named styles provide reusable renderer-facing colors and text sizing, including normal, hover,
pressed and focused button states. Per-widget opacity and animation are applied to the same runtime
controls rather than a separate editor-only representation.

Animation playback samples immutable clips at an absolute bounded time. `play`, `pause`, `resume`,
`stop`, `seek`, `step`, `layout` and `update` never attempt unbounded catch-up. Serialized tracks may
only target the explicitly supported UI properties; arbitrary Python paths and callbacks are not
accepted.

## Integrated editor preview

The unified SwirEditor receives a UI Designer panel above the existing M7 lighting frontend in the
cooperative application hierarchy. The project session owns one `EditorUIDesignerTooling22`, so
designer edits participate in normal dirty, save, reopen and unsaved-close behavior.

Preview construction creates an isolated scene and the same shipping UI runtime used by a game. The
renderer context is created lazily. Start captures the selected viewport; Pause retains the current
image; Step and Seek sample one bounded point; Stop and window close release the owned renderer.
Wide, tall and square viewport presets exercise responsive layouts. Focus and interaction-state
controls exercise the shipping toolkit state model.

Every preview reuse compares the source fingerprint with the current validated authoring document.
An edit closes and rebuilds the runtime instead of patching stale widget identities. Renderer,
layout, input or animation errors stop the preview and release its resources while leaving the
authoring document available for correction.

## Build and export

A present `config/ui-designer.json` opts a project into UI Designer export validation. The normal
`ProjectExporter` and integrated Build/Export Wizard include the document even though the default
profile includes `assets`, `scenes` and `scripts`, not the whole `config` directory. The staged
manifest records its SHA-256 digest and desktop packaging specs include it as data.

Preflight builds the production UI runtime. A malformed, oversized or escaping document, or an
explicit packaging exclusion that would omit it, fails before `export()` cleans a previous output
directory. A project without the document keeps the established exporter inventory unchanged. The
version 1 document has no external asset dependencies.

The relocation gate authors and saves a representative responsive UI, stages it through the default
Wizard, moves the stage, makes the authoring project unavailable, and launches the staged entrypoint
in a separate process. The installed-runtime variant uses isolated Python and verifies that
SwirEngine was imported from `site-packages`. It then reopens the canonical document and exercises
responsive layout, keyboard/gamepad focus and absolute animation sampling.

## Safety and determinism

- Unknown fields, duplicate ids/names, missing parents, hierarchy cycles, invalid style references,
  invalid animation bindings and non-finite values are rejected before replacing live state.
- The document is size bounded. Save uses a same-directory temporary file, flush/fsync and atomic
  replacement; a rejected reload or replacement failure preserves the previous live state.
- Project paths reject absolute, drive-relative and parent traversal forms and are re-resolved for
  containment on every file operation, including symlink changes.
- Runtime callbacks never enter JSON. Handler resolution is explicit at runtime and missing declared
  actions fail closed.
- Preview dimensions, update steps and runtime diagnostics are bounded. No FPS or cross-platform GPU
  performance claim is made.

## Focused verification

```bash
python -m pytest -q tests/test_ui_designer_authoring_2_2.py \
  tests/test_ui_designer_runtime_2_2.py tests/test_ui_designer_editor_2_2.py \
  tests/test_ui_designer_shipping_2_2.py
python -m pytest -q tests/test_ui_toolkit_2_1_5.py \
  tests/test_editor_ui_hud_tooling_2_1.py tests/test_editor_ui_hud_session_2_1.py
python tools/generate_progress_svg.py --check
```

The dedicated workflow also runs the relocated stage against a non-editable installed wheel. Native
Tk preview coverage runs under Xvfb and the relocated runtime must produce a real software-EGL
frame. These gates qualify source development only; progress can advance only after the exact PR
head is green, merges normally, and the resulting `main` head is also fully green.
