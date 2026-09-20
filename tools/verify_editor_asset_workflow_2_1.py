from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path

from swirengine.assets import AssetManager
from swirengine.editor_asset_drop21 import install_native_asset_drop21, split_external_drop_paths21
from swirengine.editor_asset_frontend21 import EditorAssetWorkflow21, create_editor_asset_pipeline21
from swirengine.editor_assets import EditorAssetBrowser


def _verify_native_drop(root: tk.Tk) -> None:
    target = tk.Frame(root)
    target.pack()
    received: list[object] = []

    status = install_native_asset_drop21(root, (target,), lambda event: received.append(event) or "copy")
    if not status.enabled or status.targets != 1:
        raise RuntimeError(f"TkDnD runtime bridge did not initialize: {status.message}")

    payload = "{/tmp/swir asset.png} /tmp/swir-map.glb {/tmp/swir asset.png}"
    paths = split_external_drop_paths21(payload, root.tk.splitlist)
    if paths != ("/tmp/swir asset.png", "/tmp/swir-map.glb"):
        raise RuntimeError(f"TkDnD Tcl payload parsing mismatch: {paths!r}")

    root.update_idletasks()


def _verify_asset_workflow(workspace: Path) -> None:
    source = workspace / "external" / "dialogue.txt"
    source.parent.mkdir(parents=True)
    source.write_text("SwirEngine 2.1 asset runtime probe\n", encoding="utf-8")

    manager = AssetManager(workspace / "project" / "assets")
    workflow = EditorAssetWorkflow21(
        create_editor_asset_pipeline21(manager, max_workers=1),
        EditorAssetBrowser(manager),
    )
    try:
        tickets = workflow.import_paths([source])
        if len(tickets) != 1 or not tickets[0].queued:
            raise RuntimeError(f"Asset import did not queue one background job: {tickets!r}")

        result = workflow.backend.wait(tickets[0], timeout=10.0)
        if not result.successful:
            raise RuntimeError(f"Asset background processing failed: {result.error}")

        frame = workflow.refresh()
        if not frame.healthy or frame.preview is None:
            raise RuntimeError(f"Imported asset did not produce a healthy preview: {frame!r}")
        if frame.preview.text != source.read_text(encoding="utf-8"):
            raise RuntimeError("Imported text preview does not match the source content")
        if frame.pipeline.diagnostics.failed:
            raise RuntimeError(f"Asset diagnostics reported failed jobs: {frame.pipeline.diagnostics!r}")
    finally:
        workflow.shutdown()


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    try:
        _verify_native_drop(root)
        with tempfile.TemporaryDirectory(prefix="swirengine-assets-2-1-") as temporary:
            _verify_asset_workflow(Path(temporary))
    finally:
        root.destroy()

    print("SwirEngine 2.1 asset workflow runtime gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
