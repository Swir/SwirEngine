from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from swirengine.editor_asset_drop21 import (
    NativeAssetDropStatus21,
    TkNativeDropAssetPipelineEditorApp21,
    install_native_asset_drop21,
    split_external_drop_paths21,
)


class _DropTarget:
    def __init__(self) -> None:
        self.registered: list[str] = []
        self.bindings: list[tuple[str, Any]] = []

    def drop_target_register(self, value: str) -> None:
        self.registered.append(value)

    def dnd_bind(self, event: str, callback: Any) -> None:
        self.bindings.append((event, callback))


def test_split_external_drop_paths_uses_tcl_list_and_deduplicates(tmp_path) -> None:
    first = tmp_path / "source assets" / "hero.png"
    second = tmp_path / "maps" / "arena.glb"

    def splitlist(_raw: str) -> tuple[str, str, str]:
        return str(first), str(second), str(first)

    assert split_external_drop_paths21("ignored", splitlist) == (str(first), str(second))


def test_split_external_drop_paths_contains_malformed_payload() -> None:
    def broken_splitlist(_raw: str) -> tuple[str, ...]:
        raise RuntimeError("bad Tcl list")

    assert split_external_drop_paths21("{folder with spaces}", broken_splitlist) == (
        "folder with spaces",
    )


def test_install_native_asset_drop_registers_all_compatible_targets() -> None:
    root = object()
    first = _DropTarget()
    second = _DropTarget()
    required: list[object] = []

    def loader():
        return (
            lambda candidate: required.append(candidate),
            "DND_Files",
            "copy",
        )

    def callback(_event: Any) -> str:
        return "copy"

    status = install_native_asset_drop21(
        root,
        (first, second),
        callback,
        loader=loader,
    )

    assert status == NativeAssetDropStatus21(
        True,
        "copy",
        "Native file/folder drag & drop ready on 2 Assets target(s).",
        2,
    )
    assert required == [root]
    assert first.registered == ["DND_Files"]
    assert second.registered == ["DND_Files"]
    assert first.bindings == [("<<Drop>>", callback)]
    assert second.bindings == [("<<Drop>>", callback)]


def test_install_native_asset_drop_falls_back_without_backend() -> None:
    def missing_loader():
        raise ImportError("missing tkinterdnd2")

    status = install_native_asset_drop21(
        object(),
        (),
        lambda _event: "copy",
        loader=missing_loader,
    )

    assert status.enabled is False
    assert status.targets == 0
    assert status.action == "copy"
    assert "Import Files/Folder" in status.message


def test_native_drop_event_routes_paths_through_existing_import_workflow(tmp_path) -> None:
    first = tmp_path / "drop one" / "hero.png"
    second = tmp_path / "drop two"
    app = TkNativeDropAssetPipelineEditorApp21.__new__(TkNativeDropAssetPipelineEditorApp21)
    app.root = SimpleNamespace(
        tk=SimpleNamespace(splitlist=lambda _raw: (str(first), str(second)))
    )
    app.native_asset_drop = NativeAssetDropStatus21(True, "copy", "ready", 2)
    imported: list[tuple[str, ...]] = []

    def run_import(paths: tuple[str, ...]) -> None:
        imported.append(paths)

    app._run_asset_import = run_import

    result = app._asset_external_drop(SimpleNamespace(data="ignored"))

    assert result == "copy"
    assert imported == [(str(first), str(second))]
