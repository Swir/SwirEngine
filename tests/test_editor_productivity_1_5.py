from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from swirengine.assets import AssetManager
from swirengine.editor15 import (
    EditorAssetAuditor,
    EditorBatchEditor,
    EditorCommandHistory,
    EditorPrefabDocument,
)
from swirengine.graphics.primitives import Rectangle2D, Sprite2D, Text2D
from swirengine.prefab import Prefab


@dataclass
class _LinkedNode:
    value: int
    name: str = ""
    peer: _LinkedNode | None = None


class _Guarded:
    def __init__(self, value: int, *, reject: int | None = None, name: str = "") -> None:
        self._value = value
        self.reject = reject
        self.name = name

    @property
    def value(self) -> int:
        return self._value

    @value.setter
    def value(self, value: int) -> None:
        if self.reject is not None and value == self.reject:
            raise ValueError("rejected")
        self._value = value


def test_prefab_document_apply_is_non_destructive_and_undoable() -> None:
    source = Prefab(Rectangle2D(1, 2, 16, 16, name="enemy"), name="enemy")
    document = EditorPrefabDocument(source)
    instance = document.instantiate()
    instance.root.x = 96

    before = document.diff(instance)
    assert before.changed_fields == 1
    assert before.fields[0].field == "x"

    result = document.apply(instance)
    assert result.changed_fields == 1
    assert result.remaining.empty
    assert document.build().instantiate().root.x == 96
    assert source.instantiate().root.x == 1

    item = document.history.undo()
    assert item.kind == "prefab_apply"
    assert document.build().instantiate().root.x == 1
    assert document.diff(instance).changed_fields == 1

    document.history.redo()
    assert document.build().instantiate().root.x == 96
    assert document.diff(instance).empty


def test_prefab_document_revert_is_selective_and_undoable() -> None:
    prefab = Prefab(Rectangle2D(1, 2, 16, 16, name="enemy"), name="enemy")
    document = EditorPrefabDocument(prefab)
    instance = document.instantiate()
    instance.root.x = 50
    instance.root.y = 75

    result = document.revert(instance, properties=["x"])
    assert result.changed_fields == 1
    assert instance.root.x == 1
    assert instance.root.y == 75
    assert result.remaining.changed_fields == 1

    document.history.undo()
    assert instance.root.x == 50
    assert instance.root.y == 75

    document.history.redo()
    assert instance.root.x == 1
    assert instance.root.y == 75


def test_prefab_graph_references_are_remapped_for_apply_and_revert() -> None:
    left = _LinkedNode(1, name="left")
    right = _LinkedNode(2, name="right")
    left.peer = right
    prefab = Prefab(left, right, name="pair")
    document = EditorPrefabDocument(prefab)

    instance = document.instantiate()
    instance.objects[0].value = 10
    instance.objects[0].peer = instance.objects[1]
    document.apply(instance)

    built = document.build().instantiate()
    assert built.objects[0].value == 10
    assert built.objects[0].peer is built.objects[1]

    instance.objects[0].peer = None
    document.revert(instance, selectors=["left"], properties=["peer"])
    assert instance.objects[0].peer is instance.objects[1]


def test_prefab_variant_is_materialized_and_independent() -> None:
    base = Prefab(Rectangle2D(0, 0, 20, 20, name="crate"), name="crate")
    document = EditorPrefabDocument(base)
    instance = document.instantiate()
    instance.root.width = 48

    variant = document.create_variant("wide_crate", instance)
    assert variant.source_name == "crate"
    assert variant.changes.changed_fields == 1
    assert variant.instantiate().root.width == 48
    assert base.instantiate().root.width == 20


def test_prefab_selector_validation_is_strict() -> None:
    document = EditorPrefabDocument(
        Prefab(
            Rectangle2D(0, 0, 8, 8, name="same"),
            Rectangle2D(10, 0, 8, 8, name="same"),
            name="pair",
        )
    )
    instance = document.instantiate()
    instance.objects[0].x = 4

    with pytest.raises(KeyError, match="ambiguous"):
        document.apply(instance, selectors=["same"])
    with pytest.raises(TypeError):
        document.apply(instance, selectors=[True])
    with pytest.raises(IndexError):
        document.apply(instance, selectors=[99])


def test_batch_edit_preview_commit_stale_guard_and_history() -> None:
    targets = [
        Rectangle2D(0, 0, 10, 10, name="a"),
        Rectangle2D(5, 5, 10, 10, name="b"),
    ]
    history = EditorCommandHistory()
    editor = EditorBatchEditor(history=history)

    plan = editor.preview(targets, {"visible": False, "layer": 3}, label="Hide enemies")
    assert plan.affected_targets == 2
    assert plan.changed_fields == 4
    result = editor.commit(plan)
    assert result.affected_targets == 2
    assert all(target.visible is False and target.layer == 3 for target in targets)

    history.undo()
    assert all(target.visible is True and target.layer == 0 for target in targets)
    history.redo()
    assert all(target.visible is False and target.layer == 3 for target in targets)

    stale = editor.preview(targets, {"layer": 9})
    targets[0].layer = 7
    with pytest.raises(RuntimeError, match="stale batch plan"):
        editor.commit(stale)
    assert targets[1].layer == 3


def test_batch_edit_rolls_back_partial_failure() -> None:
    first = _Guarded(1, name="first")
    second = _Guarded(2, reject=9, name="second")
    editor = EditorBatchEditor()

    plan = editor.preview([first, second], {"value": 9})
    with pytest.raises(ValueError, match="rejected"):
        editor.commit(plan)

    assert first.value == 1
    assert second.value == 2
    assert not editor.history.frame().can_undo


def test_command_history_is_bounded_and_redo_clears_on_new_edit() -> None:
    history = EditorCommandHistory(capacity=2)
    state = {"value": 0}

    for value in (1, 2, 3):
        before = state["value"]
        state["value"] = value
        history.record_applied(
            f"set {value}",
            kind="test",
            affected=1,
            undo=lambda before=before: state.__setitem__("value", before),
            redo=lambda value=value: state.__setitem__("value", value),
        )

    assert [item.label for item in history.frame().undo] == ["set 2", "set 3"]
    history.undo()
    assert state["value"] == 2

    state["value"] = 8
    history.record_applied(
        "set 8",
        kind="test",
        affected=1,
        undo=lambda: state.__setitem__("value", 2),
        redo=lambda: state.__setitem__("value", 8),
    )
    assert not history.frame().can_redo


def test_asset_auditor_reports_missing_unsafe_alias_and_unused_assets(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    (assets / "textures").mkdir(parents=True)
    (assets / "audio").mkdir()
    (assets / "textures" / "hero.png").write_bytes(b"png")
    (assets / "textures" / "unused.png").write_bytes(b"unused")
    (assets / "audio" / "theme.ogg").write_bytes(b"ogg")

    manager = AssetManager(assets)
    manager.register("theme", "audio/theme.ogg")
    manager.register("missing_alias", "audio/missing.ogg")

    hero = Sprite2D("textures/hero.png", name="hero")
    missing_font = Text2D("hello", font="fonts/missing.ttf", name="label")
    unsafe = Sprite2D("../outside.png", name="unsafe")
    alias_holder = Sprite2D("theme", name="music_alias")

    frame = EditorAssetAuditor(manager).scan([hero, missing_font, unsafe, alias_holder])

    assert {reference.path for reference in frame.missing} == {"fonts/missing.ttf"}
    assert {reference.path for reference in frame.unsafe} == {"../outside.png"}
    assert frame.missing_aliases == ("missing_alias",)
    assert "textures/unused.png" in frame.unused_assets
    assert "textures/hero.png" not in frame.unused_assets
    assert "audio/theme.ogg" not in frame.unused_assets
    assert not frame.healthy


def test_asset_auditor_ignores_regular_text_values(tmp_path: Path) -> None:
    manager = AssetManager(tmp_path / "assets")
    text = Text2D("hello world", name="label")
    frame = EditorAssetAuditor(manager).scan([text])
    assert frame.references == ()
    assert frame.healthy
