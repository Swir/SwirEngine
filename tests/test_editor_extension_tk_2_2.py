from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from swirengine.editor_extension_frontend22 import TkEditorExtensionHostApp22
from swirengine.editor_extension_sdk22 import (
    EditorExtensionAction22,
    EditorExtensionCapability22,
    EditorExtensionContext22,
    EditorExtensionManifest22,
    EditorExtensionPanel22,
    EditorExtensionRegistry22,
    EditorExtensionRow22,
)
from swirengine.editor_ui_designer_frontend22 import TkUIDesignerEditorApp22


class _DynamicExtension:
    def __init__(self, extension_id: str, name: str) -> None:
        self.manifest = EditorExtensionManifest22(
            extension_id,
            name,
            "1.0",
            (
                EditorExtensionCapability22.PANELS,
                EditorExtensionCapability22.ACTIONS,
            ),
        )
        self.context: EditorExtensionContext22 | None = None
        self.refreshes = 0
        self.unloaded = False

    def on_load(self, context: EditorExtensionContext22) -> None:
        self.context = context
        context.publish_panel(EditorExtensionPanel22("a-panel", "A panel"))
        self._publish_status()

    def on_unload(self) -> None:
        self.unloaded = True

    def _publish_status(self) -> None:
        assert self.context is not None
        self.context.publish_panel(
            EditorExtensionPanel22(
                "z-panel",
                "Z panel",
                rows=(
                    EditorExtensionRow22(
                        "refreshes",
                        "Refreshes",
                        str(self.refreshes),
                    ),
                ),
                actions=(
                    EditorExtensionAction22("refresh", "Refresh"),
                    EditorExtensionAction22("disabled", "Disabled", enabled=False),
                    EditorExtensionAction22("fail", "Fail safely"),
                ),
            ),
            handlers={
                "refresh": self._refresh,
                "disabled": self._disabled,
                "fail": self._fail,
            },
        )

    def _refresh(self) -> None:
        self.refreshes += 1
        self._publish_status()

    @staticmethod
    def _disabled() -> None:
        raise AssertionError("disabled action must not run")

    @staticmethod
    def _fail() -> None:
        raise RuntimeError("private extension callback detail")


class _OverviewExtension:
    def __init__(self) -> None:
        self.manifest = EditorExtensionManifest22(
            "alpha",
            "Alpha",
            "1.0",
            (EditorExtensionCapability22.PANELS,),
        )

    def on_load(self, context: EditorExtensionContext22) -> None:
        context.publish_panel(
            EditorExtensionPanel22(
                "overview",
                "Overview",
                rows=(EditorExtensionRow22("state", "State", "Ready"),),
            )
        )


class _FakeStringVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _FakeWidget:
    def __init__(self, master: Any = None, **kwargs: Any) -> None:
        self.master = master
        self.options = dict(kwargs)
        self.children: list[_FakeWidget] = []
        self.destroyed = False
        if isinstance(master, _FakeWidget):
            master.children.append(self)

    def grid(self, **kwargs: Any) -> None:
        self.grid_options = kwargs

    def pack(self, **kwargs: Any) -> None:
        self.pack_options = kwargs

    def configure(self, **kwargs: Any) -> None:
        self.options.update(kwargs)

    config = configure

    def cget(self, name: str) -> Any:
        return self.options.get(name)

    def columnconfigure(self, _column: int, **_kwargs: Any) -> None:
        return None

    def rowconfigure(self, _row: int, **_kwargs: Any) -> None:
        return None

    def destroy(self) -> None:
        self.destroyed = True
        for child in tuple(self.children):
            child.destroy()

    def winfo_exists(self) -> bool:
        return not self.destroyed


class _FakeWindow(_FakeWidget):
    def title(self, value: str) -> None:
        self.window_title = value

    def geometry(self, value: str) -> None:
        self.window_geometry = value

    def minsize(self, width: int, height: int) -> None:
        self.minimum_size = (width, height)

    def transient(self, parent: Any) -> None:
        self.transient_parent = parent

    def protocol(self, name: str, callback: Any) -> None:
        self.protocols = {name: callback}

    def deiconify(self) -> None:
        self.deiconified = True

    def lift(self) -> None:
        self.lifted = True


class _FakeRoot(_FakeWindow):
    def __init__(self) -> None:
        super().__init__()
        self.after_callbacks: dict[str, Any] = {}
        self.cancelled: list[str] = []
        self._after_index = 0

    def after(self, _delay: int, callback: Any) -> str:
        self._after_index += 1
        token = f"after-{self._after_index}"
        self.after_callbacks[token] = callback
        return token

    def after_cancel(self, token: str) -> None:
        self.cancelled.append(token)
        self.after_callbacks.pop(token, None)


class _FakeNotebook(_FakeWidget):
    def __init__(self, master: Any = None, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._tabs: list[_FakeWidget] = []
        self.tab_labels: list[str] = []

    def add(self, child: _FakeWidget, *, text: str) -> None:
        self._tabs.append(child)
        self.tab_labels.append(text)

    def tabs(self) -> tuple[_FakeWidget, ...]:
        return tuple(self._tabs)

    @staticmethod
    def nametowidget(tab_id: _FakeWidget) -> _FakeWidget:
        return tab_id

    def forget(self, tab_id: _FakeWidget) -> None:
        index = self._tabs.index(tab_id)
        self._tabs.pop(index)
        self.tab_labels.pop(index)


class _FakeButton(_FakeWidget):
    def invoke(self) -> None:
        if self.options.get("state") != "disabled":
            self.options["command"]()


class _FakeMenu:
    def __init__(self) -> None:
        self.commands: list[dict[str, Any]] = []

    def add_command(self, **kwargs: Any) -> None:
        self.commands.append(kwargs)


class _FakeTk:
    Toplevel = _FakeWindow
    StringVar = _FakeStringVar


class _FakeTtk:
    Frame = _FakeWidget
    Label = _FakeWidget
    Notebook = _FakeNotebook
    Button = _FakeButton


def test_fake_tk_host_renders_dynamic_declarations_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_closes: list[bool] = []

    def init_base(self: Any, controller: Any, **_kwargs: Any) -> None:
        self.tk, self.ttk = _FakeTk, _FakeTtk
        self.controller = controller
        self.root = _FakeRoot()

    monkeypatch.setattr(TkUIDesignerEditorApp22, "__init__", init_base)
    monkeypatch.setattr(
        TkUIDesignerEditorApp22,
        "install_creator_menu",
        lambda _self, _menu: None,
    )
    monkeypatch.setattr(
        TkUIDesignerEditorApp22,
        "close",
        lambda _self: base_closes.append(True),
    )

    registry = EditorExtensionRegistry22()
    dynamic = _DynamicExtension("zulu", "Zulu")
    registry.register(dynamic)
    registry.register(_OverviewExtension())
    errors: list[tuple[object, ...]] = []
    controller = SimpleNamespace(
        console=SimpleNamespace(write=lambda *args, **kwargs: errors.append((*args, kwargs)))
    )
    app = TkEditorExtensionHostApp22(controller, editor_extensions=registry)
    menu = _FakeMenu()
    app.install_creator_menu(menu)
    assert [item["label"] for item in menu.commands] == ["Editor Extensions..."]

    app._open_editor_extensions()
    first_window = app._editor_extension_window
    after_token = app._editor_extension_after
    assert app._editor_extension_notebook.tab_labels == ["Alpha", "Zulu"]
    zulu_frame = app._editor_extension_notebook.tabs()[1]
    panel_notebook = next(
        child for child in zulu_frame.children if isinstance(child, _FakeNotebook)
    )
    assert panel_notebook.tab_labels == ["A panel", "Z panel"]
    assert app._editor_extension_row_values[("zulu", "z-panel", "refreshes")].cget("text") == "0"
    assert app._editor_extension_action_buttons[("zulu", "disabled")].cget("state") == ("disabled")

    app._editor_extension_action_buttons[("zulu", "refresh")].invoke()
    assert dynamic.refreshes == 1
    assert app._editor_extension_row_values[("zulu", "z-panel", "refreshes")].cget("text") == "1"
    app._editor_extension_action_buttons[("zulu", "fail")].invoke()
    assert app._editor_extension_status.get() == "Extension action failed."
    assert errors[-1][0] == "Extension action failed."
    assert "private extension" not in repr(errors)

    app._close_editor_extensions()
    assert first_window.destroyed
    assert app._editor_extension_window is None
    assert after_token in app.root.cancelled
    assert len(registry) == 2
    app._open_editor_extensions()
    assert app._editor_extension_window is not first_window

    app.close()
    assert base_closes == [True]
    assert len(registry) == 0
    assert dynamic.unloaded
    assert dynamic.context is not None and not dynamic.context.active
    assert app._editor_extension_window is None


def test_snapshot_provider_failure_is_sanitized_in_fake_tk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def init_base(self: Any, controller: Any, **_kwargs: Any) -> None:
        self.tk, self.ttk = _FakeTk, _FakeTtk
        self.controller = controller
        self.root = _FakeRoot()

    monkeypatch.setattr(TkUIDesignerEditorApp22, "__init__", init_base)
    monkeypatch.setattr(TkUIDesignerEditorApp22, "close", lambda _self: None)
    registry = EditorExtensionRegistry22()
    messages: list[str] = []
    controller = SimpleNamespace(
        console=SimpleNamespace(write=lambda message, **_kwargs: messages.append(str(message)))
    )
    app = TkEditorExtensionHostApp22(controller, editor_extensions=registry)
    original_snapshot = registry.snapshot

    def fail_snapshot() -> Any:
        raise RuntimeError("private registry detail")

    registry.snapshot = fail_snapshot  # type: ignore[method-assign]
    try:
        app._open_editor_extensions()
        assert app._editor_extension_status.get() == "Editor extension operation failed."
        assert messages == ["Editor extension operation failed."]
        assert "private registry" not in repr(messages)
    finally:
        registry.snapshot = original_snapshot  # type: ignore[method-assign]
        app.close()


def test_stale_extension_window_cannot_block_registry_or_base_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tkinter import TclError

    base_closes: list[bool] = []

    def init_base(self: Any, controller: Any, **_kwargs: Any) -> None:
        self.tk, self.ttk = _FakeTk, _FakeTtk
        self.controller = controller
        self.root = _FakeRoot()

    class StaleWindow:
        @staticmethod
        def destroy() -> None:
            raise TclError("private stale Tk detail")

    monkeypatch.setattr(TkUIDesignerEditorApp22, "__init__", init_base)
    monkeypatch.setattr(
        TkUIDesignerEditorApp22,
        "close",
        lambda _self: base_closes.append(True),
    )
    registry = EditorExtensionRegistry22()
    extension = _DynamicExtension("stale", "Stale")
    registry.register(extension)
    messages: list[str] = []
    controller = SimpleNamespace(
        console=SimpleNamespace(write=lambda message, **_kwargs: messages.append(str(message)))
    )
    app = TkEditorExtensionHostApp22(controller, editor_extensions=registry)
    app._editor_extension_window = StaleWindow()

    app.close()

    assert base_closes == [True]
    assert len(registry) == 0
    assert extension.unloaded
    assert extension.context is not None and not extension.context.active
    assert app._editor_extensions_shutdown is True
    assert "private stale Tk detail" not in repr(messages)


def test_native_tk_extension_host_close_reopen_and_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("SWIR_EDITOR_EXTENSIONS_REQUIRE_TK") != "1":
        pytest.skip("required by the dedicated Xvfb native Tk workflow")
    import tkinter as tk
    from tkinter import ttk

    base_closes: list[bool] = []

    def init_base(self: Any, controller: Any, **_kwargs: Any) -> None:
        self.tk, self.ttk = tk, ttk
        self.controller = controller
        self.root = tk.Tk()
        self.root.geometry("220x120")

    def close_base(self: Any) -> None:
        base_closes.append(True)
        self.root.destroy()

    monkeypatch.setattr(TkUIDesignerEditorApp22, "__init__", init_base)
    monkeypatch.setattr(TkUIDesignerEditorApp22, "close", close_base)

    registry = EditorExtensionRegistry22()
    extension = _DynamicExtension("native", "Native")
    registry.register(extension)
    errors: list[tuple[object, ...]] = []
    controller = SimpleNamespace(
        console=SimpleNamespace(write=lambda *args, **kwargs: errors.append((*args, kwargs)))
    )
    app = TkEditorExtensionHostApp22(controller, editor_extensions=registry)
    callbacks: list[tuple[object, ...]] = []
    app.root.report_callback_exception = lambda *args: callbacks.append(args)
    closed = False
    try:
        app._open_editor_extensions()
        app.root.update()
        first_window = app._editor_extension_window
        assert len(app._editor_extension_notebook.tabs()) == 1
        assert first_window.winfo_width() >= 720
        assert app._editor_extension_action_buttons[("native", "disabled")].instate(("disabled",))

        app._editor_extension_action_buttons[("native", "refresh")].invoke()
        app.root.update()
        assert extension.refreshes == 1
        assert (
            app._editor_extension_row_values[("native", "z-panel", "refreshes")].cget("text") == "1"
        )

        app._close_editor_extensions()
        app.root.update()
        assert app._editor_extension_window is None
        app._open_editor_extensions()
        app.root.update()
        assert app._editor_extension_window is not first_window
        app.close()
        closed = True
        assert base_closes == [True]
        assert len(registry) == 0
        assert extension.unloaded
        assert extension.context is not None and not extension.context.active
        assert not callbacks and not errors
    finally:
        if not closed:
            app.close()
