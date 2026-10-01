from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from swirengine.editor_extension_sdk22 import (
    MAX_EXTENSION_ACTIONS_PER_PANEL_22,
    MAX_EXTENSION_ROWS_PER_PANEL_22,
    EditorExtensionAction22,
    EditorExtensionCapability22,
    EditorExtensionContext22,
    EditorExtensionLifecycleError22,
    EditorExtensionManifest22,
    EditorExtensionPanel22,
    EditorExtensionRegistry22,
    EditorExtensionRow22,
    EditorExtensionRowTone22,
    EditorExtensionValidationError22,
)


def _manifest(
    extension_id: str,
    *capabilities: EditorExtensionCapability22,
) -> EditorExtensionManifest22:
    return EditorExtensionManifest22(
        extension_id=extension_id,
        name=f"Extension {extension_id}",
        version="1.0",
        capabilities=capabilities,
    )


class _PanelExtension:
    def __init__(
        self,
        extension_id: str,
        *,
        panel_id: str = "status",
        value: str = "Ready",
    ) -> None:
        self.manifest = _manifest(
            extension_id,
            EditorExtensionCapability22.ACTIONS,
            EditorExtensionCapability22.PANELS,
        )
        self.panel_id = panel_id
        self.value = value
        self.calls = 0
        self.context: EditorExtensionContext22 | None = None
        self.unloaded = False

    def on_load(self, context: EditorExtensionContext22) -> None:
        self.context = context
        context.publish_panel(
            EditorExtensionPanel22(
                panel_id=self.panel_id,
                title=f"Panel {self.panel_id}",
                rows=(EditorExtensionRow22("state", "State", self.value),),
                actions=(EditorExtensionAction22("refresh", "Refresh"),),
            ),
            handlers={"refresh": self._refresh},
        )

    def on_unload(self) -> None:
        self.unloaded = True

    def _refresh(self) -> None:
        self.calls += 1


def test_registry_is_explicit_deterministic_and_snapshot_only() -> None:
    registry = EditorExtensionRegistry22()
    second = _PanelExtension("Zulu", panel_id="z-panel", value="Second")
    first = _PanelExtension("alpha", panel_id="b-panel", value="First")
    registry.register(second)
    registry.register(first)
    assert first.context is not None
    first.context.publish_panel(
        EditorExtensionPanel22("A-panel", "First panel"),
    )

    snapshot = registry.snapshot()
    assert [view.manifest.extension_id for view in snapshot.extensions] == ["alpha", "Zulu"]
    assert [panel.panel_id for panel in snapshot.extensions[0].panels] == [
        "A-panel",
        "b-panel",
    ]
    assert snapshot.extensions[0].panels[1].rows[0].value == "First"
    assert "callback" not in repr(snapshot).casefold()
    assert "_refresh" not in repr(snapshot)

    with pytest.raises(FrozenInstanceError):
        snapshot.extensions[0].manifest.name = "mutated"  # type: ignore[misc]
    result = registry.invoke_action("ALPHA", "REFRESH")
    assert (result.ok, result.code, first.calls) == (True, "ok", 1)


def test_context_exposes_only_bounded_declarative_surface() -> None:
    public_names = {name for name in dir(EditorExtensionContext22) if not name.startswith("_")}
    assert public_names == {
        "active",
        "capabilities",
        "extension_id",
        "publish_panel",
        "remove_panel",
    }
    forbidden = {"app", "session", "root", "scene", "renderer", "plugin_manager"}
    assert public_names.isdisjoint(forbidden)
    assert not hasattr(EditorExtensionRegistry22, "autoload")
    assert not hasattr(EditorExtensionRegistry22, "discover")
    assert not hasattr(EditorExtensionRegistry22, "load_module")


def test_sdk_provider_failures_have_no_hidden_exception_context() -> None:
    capability_secret = "private allowed capability provider detail"
    manifest_secret = "private manifest provider detail"
    handlers_secret = "private handler mapping detail"

    class FailingCapabilities:
        @staticmethod
        def __iter__():
            raise RuntimeError(capability_secret)

    class FailingManifest:
        @property
        def manifest(self):
            raise RuntimeError(manifest_secret)

    class FailingHandlers(dict):
        def items(self):
            raise RuntimeError(handlers_secret)

    with pytest.raises(EditorExtensionValidationError22) as capabilities:
        EditorExtensionRegistry22(allowed_capabilities=FailingCapabilities())  # type: ignore[arg-type]
    with pytest.raises(EditorExtensionLifecycleError22) as manifest:
        EditorExtensionRegistry22().register(FailingManifest())  # type: ignore[arg-type]

    extension = _PanelExtension("mapping")
    registry = EditorExtensionRegistry22()
    registry.register(extension)
    assert extension.context is not None
    with pytest.raises(EditorExtensionValidationError22) as handlers:
        extension.context.publish_panel(
            EditorExtensionPanel22(
                "provider",
                "Provider",
                actions=(EditorExtensionAction22("run", "Run"),),
            ),
            handlers=FailingHandlers(),
        )

    for caught, secret in (
        (capabilities.value, capability_secret),
        (manifest.value, manifest_secret),
        (handlers.value, handlers_secret),
    ):
        assert caught.__cause__ is None
        assert caught.__context__ is None
        assert secret not in repr(caught)


def test_capability_and_handler_iterables_have_hard_read_bounds() -> None:
    class ManyCapabilities:
        def __init__(self) -> None:
            self.consumed = 0

        def __iter__(self):
            for _index in range(100):
                self.consumed += 1
                yield EditorExtensionCapability22.PANELS

    capabilities = ManyCapabilities()
    with pytest.raises(EditorExtensionValidationError22, match="item limit"):
        EditorExtensionRegistry22(allowed_capabilities=capabilities)
    assert capabilities.consumed == len(EditorExtensionCapability22) + 1

    class ManyHandlers(dict):
        def __init__(self) -> None:
            super().__init__()
            self.consumed = 0

        def __len__(self) -> int:
            return 1

        def items(self):
            for index in range(100):
                self.consumed += 1
                yield f"action-{index}", lambda: None

    extension = _PanelExtension("bounded-handlers")
    registry = EditorExtensionRegistry22()
    registry.register(extension)
    assert extension.context is not None
    handlers = ManyHandlers()
    with pytest.raises(EditorExtensionValidationError22, match="changed while being read"):
        extension.context.publish_panel(
            EditorExtensionPanel22(
                "bounded",
                "Bounded",
                actions=(EditorExtensionAction22("run", "Run"),),
            ),
            handlers=handlers,
        )
    assert handlers.consumed == MAX_EXTENSION_ACTIONS_PER_PANEL_22 + 1


def test_capabilities_are_explicit_host_and_extension_gates() -> None:
    extension = _PanelExtension("denied")
    registry = EditorExtensionRegistry22(allowed_capabilities=(EditorExtensionCapability22.PANELS,))
    with pytest.raises(EditorExtensionValidationError22, match="host did not allow"):
        registry.register(extension)
    assert len(registry) == 0

    class MissingActionCapability:
        manifest = _manifest("missing-action", EditorExtensionCapability22.PANELS)

        def on_load(self, context: EditorExtensionContext22) -> None:
            context.publish_panel(
                EditorExtensionPanel22(
                    "panel",
                    "Panel",
                    actions=(EditorExtensionAction22("run", "Run"),),
                ),
                handlers={"run": lambda: None},
            )

    with pytest.raises(EditorExtensionLifecycleError22, match="extension load failed"):
        EditorExtensionRegistry22().register(MissingActionCapability())


def test_casefold_collisions_are_rejected_at_every_lookup_scope() -> None:
    registry = EditorExtensionRegistry22()
    extension = _PanelExtension("Tools", panel_id="Network")
    registry.register(extension)
    with pytest.raises(EditorExtensionValidationError22, match="collides"):
        registry.register(_PanelExtension("tools"))
    assert extension.context is not None
    with pytest.raises(EditorExtensionValidationError22, match="panel_id collides"):
        extension.context.publish_panel(EditorExtensionPanel22("network", "Other"))

    with pytest.raises(EditorExtensionValidationError22, match="row_id values collide"):
        EditorExtensionPanel22(
            "rows",
            "Rows",
            rows=(
                EditorExtensionRow22("Latency", "Latency", "1 ms"),
                EditorExtensionRow22("latency", "Latency", "2 ms"),
            ),
        )
    with pytest.raises(EditorExtensionValidationError22, match="action_id values collide"):
        EditorExtensionPanel22(
            "actions",
            "Actions",
            actions=(
                EditorExtensionAction22("Capture", "Capture"),
                EditorExtensionAction22("capture", "Capture again"),
            ),
        )


def test_cross_panel_action_collision_and_handler_shape_are_rejected() -> None:
    registry = EditorExtensionRegistry22()
    extension = _PanelExtension("debugger")
    registry.register(extension)
    assert extension.context is not None
    with pytest.raises(EditorExtensionValidationError22, match="another extension panel"):
        extension.context.publish_panel(
            EditorExtensionPanel22(
                "capture",
                "Capture",
                actions=(EditorExtensionAction22("REFRESH", "Again"),),
            ),
            handlers={"refresh": lambda: None},
        )
    with pytest.raises(EditorExtensionValidationError22, match="match"):
        extension.context.publish_panel(
            EditorExtensionPanel22(
                "mismatch",
                "Mismatch",
                actions=(EditorExtensionAction22("save", "Save"),),
            ),
            handlers={},
        )
    with pytest.raises(EditorExtensionValidationError22, match="strings"):
        extension.context.publish_panel(
            EditorExtensionPanel22(
                "bad-key",
                "Bad key",
                actions=(EditorExtensionAction22("save", "Save"),),
            ),
            handlers={1: lambda: None},  # type: ignore[dict-item]
        )
    with pytest.raises(EditorExtensionValidationError22, match="callable"):
        extension.context.publish_panel(
            EditorExtensionPanel22(
                "bad-value",
                "Bad value",
                actions=(EditorExtensionAction22("save", "Save"),),
            ),
            handlers={"save": object()},  # type: ignore[dict-item]
        )


def test_callback_failure_is_sanitized_and_does_not_remove_extension() -> None:
    secret = "private-token-123"

    class FailingAction:
        manifest = _manifest(
            "failure",
            EditorExtensionCapability22.PANELS,
            EditorExtensionCapability22.ACTIONS,
        )

        def on_load(self, context: EditorExtensionContext22) -> None:
            def fail() -> None:
                raise RuntimeError(secret)

            context.publish_panel(
                EditorExtensionPanel22(
                    "errors",
                    "Errors",
                    actions=(EditorExtensionAction22("fail", "Fail"),),
                ),
                handlers={"fail": fail},
            )

    registry = EditorExtensionRegistry22()
    registry.register(FailingAction())
    result = registry.invoke_action("failure", "fail")
    assert result == type(result)(False, "callback_failed", "Extension action failed.")
    assert secret not in str(result)
    assert secret not in repr(result)
    assert registry.is_registered("FAILURE")


def test_disabled_action_does_not_run_callback() -> None:
    calls: list[str] = []

    class DisabledAction:
        manifest = _manifest(
            "disabled",
            EditorExtensionCapability22.PANELS,
            EditorExtensionCapability22.ACTIONS,
        )

        def on_load(self, context: EditorExtensionContext22) -> None:
            context.publish_panel(
                EditorExtensionPanel22(
                    "panel",
                    "Panel",
                    actions=(EditorExtensionAction22("run", "Run", enabled=False),),
                ),
                handlers={"run": lambda: calls.append("run")},
            )

    registry = EditorExtensionRegistry22()
    registry.register(DisabledAction())
    result = registry.invoke_action("disabled", "run")
    assert (result.ok, result.code, calls) == (False, "disabled", [])


def test_failed_load_rolls_back_and_hides_sensitive_exception() -> None:
    secret = "do-not-expose-load-detail"

    class FailingLoad:
        manifest = _manifest("failing-load", EditorExtensionCapability22.PANELS)

        def __init__(self) -> None:
            self.resource_open = False
            self.unload_calls = 0

        def on_load(self, context: EditorExtensionContext22) -> None:
            context.publish_panel(EditorExtensionPanel22("temporary", "Temporary"))
            self.context = context
            self.resource_open = True
            raise RuntimeError(secret)

        def on_unload(self) -> None:
            assert not self.context.active
            self.unload_calls += 1
            self.resource_open = False

    extension = FailingLoad()
    registry = EditorExtensionRegistry22()
    with pytest.raises(EditorExtensionLifecycleError22) as caught:
        registry.register(extension)
    assert str(caught.value) == "extension load failed"
    assert secret not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert len(registry) == 0
    assert not extension.context.active
    assert extension.unload_calls == 1
    assert not extension.resource_open
    with pytest.raises(EditorExtensionLifecycleError22, match="no longer active"):
        extension.context.publish_panel(EditorExtensionPanel22("late", "Late"))


def test_failed_load_cleanup_failure_stays_sanitized_and_fully_rolled_back() -> None:
    load_secret = "do-not-expose-primary-load-detail"
    cleanup_secret = "do-not-expose-cleanup-detail"

    class FailingLoadAndCleanup:
        manifest = _manifest("failing-cleanup", EditorExtensionCapability22.PANELS)

        def __init__(self) -> None:
            self.unload_calls = 0
            self.context: EditorExtensionContext22 | None = None

        def on_load(self, context: EditorExtensionContext22) -> None:
            self.context = context
            context.publish_panel(EditorExtensionPanel22("temporary", "Temporary"))
            raise RuntimeError(load_secret)

        def on_unload(self) -> None:
            self.unload_calls += 1
            raise RuntimeError(cleanup_secret)

    extension = FailingLoadAndCleanup()
    registry = EditorExtensionRegistry22()
    with pytest.raises(EditorExtensionLifecycleError22) as caught:
        registry.register(extension)

    assert str(caught.value) == "extension load failed"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert load_secret not in repr(caught.value)
    assert cleanup_secret not in repr(caught.value)
    assert extension.unload_calls == 1
    assert extension.context is not None and not extension.context.active
    assert registry.snapshot().extensions == ()


def test_unload_cleans_panels_handlers_and_context_even_when_hook_fails() -> None:
    secret = "do-not-expose-unload-detail"

    class FailingUnload(_PanelExtension):
        def on_unload(self) -> None:
            raise RuntimeError(secret)

    extension = FailingUnload("cleanup")
    registry = EditorExtensionRegistry22()
    registry.register(extension)
    assert extension.context is not None
    with pytest.raises(EditorExtensionLifecycleError22) as caught:
        registry.unregister("CLEANUP")
    assert str(caught.value) == "extension unload failed"
    assert secret not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert len(registry) == 0
    assert registry.snapshot().extensions == ()
    assert not extension.context.active
    with pytest.raises(EditorExtensionLifecycleError22, match="no longer active"):
        extension.context.remove_panel("status")
    with pytest.raises(EditorExtensionValidationError22, match="not registered"):
        registry.invoke_action("cleanup", "refresh")


def test_unregister_removes_normal_extension_and_calls_hook() -> None:
    extension = _PanelExtension("normal")
    registry = EditorExtensionRegistry22()
    registry.register(extension)
    manifest = registry.unregister("normal")
    assert manifest.extension_id == "normal"
    assert extension.unloaded
    assert extension.context is not None and not extension.context.active
    assert registry.snapshot().extensions == ()


def test_declarative_values_are_bounded_immutable_and_control_free() -> None:
    with pytest.raises(EditorExtensionValidationError22, match="immutable tuple"):
        EditorExtensionPanel22("panel", "Panel", rows=[])  # type: ignore[arg-type]
    with pytest.raises(EditorExtensionValidationError22, match="item limit"):
        EditorExtensionPanel22(
            "panel",
            "Panel",
            rows=tuple(
                EditorExtensionRow22(f"row-{index}", "Row", str(index))
                for index in range(MAX_EXTENSION_ROWS_PER_PANEL_22 + 1)
            ),
        )
    with pytest.raises(EditorExtensionValidationError22, match="control"):
        EditorExtensionRow22("row", "Bad\nlabel", "value")
    with pytest.raises(EditorExtensionValidationError22, match="ASCII"):
        EditorExtensionAction22("akcja-\u0105", "Invalid ID")
    row = EditorExtensionRow22(
        "latency",
        "Latency",
        "12 ms",
        EditorExtensionRowTone22.GOOD,
    )
    with pytest.raises(FrozenInstanceError):
        row.value = "changed"  # type: ignore[misc]


def test_shutdown_attempts_all_unloads_and_leaves_registry_empty() -> None:
    events: list[str] = []

    class Extension(_PanelExtension):
        def __init__(self, extension_id: str, *, fail: bool) -> None:
            super().__init__(extension_id)
            self.fail = fail

        def on_unload(self) -> None:
            events.append(self.manifest.extension_id)
            if self.fail:
                raise RuntimeError("private shutdown error")

    registry = EditorExtensionRegistry22()
    registry.register(Extension("alpha", fail=True))
    registry.register(Extension("zulu", fail=False))
    with pytest.raises(EditorExtensionLifecycleError22, match="one or more"):
        registry.shutdown()
    assert events == ["zulu", "alpha"]
    assert registry.snapshot().extensions == ()
