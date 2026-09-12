from __future__ import annotations

import pytest

from swirengine import HotReloadSnapshot, HotReloadStateError, HotReloadStateRegistry


def test_atomic_restore_rolls_back_every_touched_domain_on_failure() -> None:
    state = {
        "selection": "player",
        "score": 10,
        "viewport": "perspective",
    }
    registry = HotReloadStateRegistry()

    registry.register(
        "selection",
        lambda: state["selection"],
        lambda value: state.__setitem__("selection", str(value)),
        domain="editor",
    )

    def restore_score(value: object) -> None:
        score = int(value)
        state["score"] = score
        if score == 999:
            raise RuntimeError("score rejected")

    registry.register(
        "score",
        lambda: state["score"],
        restore_score,
        domain="game",
    )
    registry.register(
        "viewport",
        lambda: state["viewport"],
        lambda value: state.__setitem__("viewport", str(value)),
        domain="editor",
    )

    requested = HotReloadSnapshot(
        (
            ("selection", "enemy"),
            ("score", 999),
            ("viewport", "top"),
        )
    )

    with pytest.raises(HotReloadStateError, match="transaction rolled back"):
        registry.restore_atomic(requested)

    assert state == {
        "selection": "player",
        "score": 10,
        "viewport": "perspective",
    }


def test_atomic_restore_captures_all_rollback_values_before_mutation() -> None:
    state = {"a": 1, "b": 2}
    registry = HotReloadStateRegistry()
    registry.register("a", lambda: state["a"], lambda value: state.__setitem__("a", int(value)))
    registry.register(
        "b",
        lambda: (_ for _ in ()).throw(RuntimeError("cannot snapshot b")),
        lambda value: state.__setitem__("b", int(value)),
    )

    with pytest.raises(HotReloadStateError, match="failed to capture rollback state 'b'"):
        registry.restore_atomic(HotReloadSnapshot((("a", 100), ("b", 200))))

    assert state == {"a": 1, "b": 2}


def test_atomic_restore_reports_rollback_failure() -> None:
    state = {"value": "stable"}
    registry = HotReloadStateRegistry()

    def restore(value: object) -> None:
        text = str(value)
        if text == "broken":
            state["value"] = "partially-mutated"
            raise RuntimeError("apply failed")
        if text == "stable":
            raise RuntimeError("rollback failed")
        state["value"] = text

    registry.register("value", lambda: state["value"], restore)

    with pytest.raises(HotReloadStateError, match="rollback failed for 'value'"):
        registry.restore_atomic(HotReloadSnapshot((("value", "broken"),)))

    assert state["value"] == "partially-mutated"


def test_domain_atomic_restore_preserves_domain_boundary() -> None:
    state = {"editor": "idle", "game": "ready"}
    registry = HotReloadStateRegistry()
    editor = registry.domain("editor")
    game = registry.domain("game")
    editor.register(
        "selection",
        lambda: state["editor"],
        lambda value: state.__setitem__("editor", str(value)),
    )
    game.register(
        "score",
        lambda: state["game"],
        lambda value: state.__setitem__("game", str(value)),
    )

    with pytest.raises(HotReloadStateError, match="does not belong to domain 'editor'"):
        editor.restore_atomic(game.capture())

    assert state == {"editor": "idle", "game": "ready"}


def test_atomic_restore_can_skip_missing_provider_when_non_strict() -> None:
    state = {"value": 1}
    registry = HotReloadStateRegistry()
    registry.register(
        "present",
        lambda: state["value"],
        lambda value: state.__setitem__("value", int(value)),
    )

    registry.restore_atomic(
        HotReloadSnapshot((("missing", 100), ("present", 5))),
        strict=False,
    )

    assert state["value"] == 5
