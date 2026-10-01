from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from swirengine.ui_designer22 import (
    MAX_UI_DESIGN_BYTES_22,
    EditorUIDesignerError22,
    EditorUIDesignerTooling22,
    UIAnimationKeyframeSpec22,
    UIAnimationSpec22,
    UIAnimationTrackSpec22,
    UIDesignAsset22,
    UIStyleSpec22,
    UIWidgetSpec22,
)


def design() -> UIDesignAsset22:
    return UIDesignAsset22(
        styles=(UIStyleSpec22("primary", button=(0.1, 0.2, 0.4, 1.0)),),
        widgets=(
            UIWidgetSpec22("menu", "panel", width=500, height=320),
            UIWidgetSpec22(
                "play",
                "button",
                parent="menu",
                order=1,
                text="Play",
                style="primary",
                action="start",
            ),
        ),
        animations=(
            UIAnimationSpec22(
                "pulse",
                1.0,
                (
                    UIAnimationTrackSpec22(
                        "play",
                        "opacity",
                        (
                            UIAnimationKeyframeSpec22(0.0, 1.0),
                            UIAnimationKeyframeSpec22(1.0, 0.25),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_canonical_round_trip_and_immutable_specs(tmp_path: Path) -> None:
    first = design()
    reordered = replace(
        first,
        widgets=tuple(reversed(first.widgets)),
        styles=tuple(reversed(first.styles)),
    )
    assert first == reordered
    assert first.fingerprint() == reordered.fingerprint()
    assert UIDesignAsset22.from_dict(first.to_dict()) == first

    tooling = EditorUIDesignerTooling22.open(tmp_path)
    tooling.set_asset(first)
    tooling.save()
    canonical = tooling.target.read_bytes()
    reopened = EditorUIDesignerTooling22(tmp_path)
    assert reopened.asset == first
    assert reopened.snapshot().fingerprint == first.fingerprint()
    reopened.save()
    assert reopened.target.read_bytes() == canonical
    assert not reopened.dirty

    with pytest.raises(FrozenInstanceError):
        first.widgets[0].text = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    "invalid",
    ("duplicate-field", "unknown", "version-bool", "non-finite", "oversize"),
)
@pytest.mark.parametrize("dirty", (False, True))
def test_rejected_reload_preserves_authoring_state(
    tmp_path: Path,
    invalid: str,
    dirty: bool,
) -> None:
    tooling = EditorUIDesignerTooling22(tmp_path)
    tooling.set_asset(design())
    tooling.save()
    canonical = tooling.target.read_bytes()
    if dirty:
        tooling.upsert_widget(replace(tooling.require_widget("play"), text="Launch"))
    before = tooling.asset
    payload = json.loads(canonical)
    if invalid == "unknown":
        payload["widgets"][0]["injected"] = True
    elif invalid == "version-bool":
        payload["version"] = True
    elif invalid == "non-finite":
        payload["widgets"][0]["width"] = float("nan")
    raw = json.dumps(payload).encode("utf-8")
    if invalid == "duplicate-field":
        raw = (
            b'{"format":"swirengine.ui-designer","version":1,"version":1,'
            b'"widgets":[]}'
        )
    elif invalid == "oversize":
        raw = b" " * (MAX_UI_DESIGN_BYTES_22 + 1)
    tooling.target.write_bytes(raw)

    with pytest.raises(EditorUIDesignerError22):
        tooling.reload()
    assert tooling.asset == before
    assert tooling.dirty is dirty
    assert tooling.target.read_bytes() == raw


def test_invalid_edit_is_transactional_and_hierarchy_is_bounded(tmp_path: Path) -> None:
    tooling = EditorUIDesignerTooling22(tmp_path)
    tooling.set_asset(design())
    tooling.save()
    before = tooling.snapshot()
    with pytest.raises(EditorUIDesignerError22, match="unknown parent"):
        tooling.upsert_widget(replace(tooling.require_widget("play"), parent="missing"))
    assert tooling.asset == before.asset
    assert tooling.dirty == before.dirty

    widgets = []
    parent = None
    for index in range(33):
        widget_id = f"node-{index}"
        widgets.append(UIWidgetSpec22(widget_id, "panel", parent=parent))
        parent = widget_id
    with pytest.raises(EditorUIDesignerError22, match="depth"):
        UIDesignAsset22(widgets=tuple(widgets))


def test_project_confinement_and_atomic_save_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(EditorUIDesignerError22, match="project-relative"):
        EditorUIDesignerTooling22(tmp_path, relative_path="../outside.json")
    tooling = EditorUIDesignerTooling22(tmp_path)
    tooling.set_asset(design())
    tooling.save()
    before = tooling.target.read_bytes()
    tooling.upsert_widget(replace(tooling.require_widget("play"), text="Launch"))

    def fail_replace(*_args: object) -> None:
        raise OSError("disk failure")

    monkeypatch.setattr("swirengine.ui_designer22.os.replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        tooling.save()
    assert tooling.dirty
    assert tooling.target.read_bytes() == before
    assert sorted(path.name for path in tooling.target.parent.iterdir()) == [
        "ui-designer.json"
    ]


def test_schema_rejects_duplicate_references_and_unbounded_animation() -> None:
    with pytest.raises(EditorUIDesignerError22, match="duplicate style"):
        UIDesignAsset22(styles=(UIStyleSpec22("x"), UIStyleSpec22("x")))
    with pytest.raises(EditorUIDesignerError22, match="unknown style"):
        UIDesignAsset22(widgets=(UIWidgetSpec22("x", "label", style="missing"),))
    with pytest.raises(EditorUIDesignerError22, match="unknown widget"):
        UIDesignAsset22(
            animations=(
                UIAnimationSpec22(
                    "bad",
                    1.0,
                    (
                        UIAnimationTrackSpec22(
                            "missing",
                            "opacity",
                            (UIAnimationKeyframeSpec22(0.0, 1.0),),
                        ),
                    ),
                ),
            )
        )
    with pytest.raises(EditorUIDesignerError22, match="opacity"):
        UIAnimationTrackSpec22(
            "x",
            "opacity",
            (UIAnimationKeyframeSpec22(0.0, 2.0),),
        )
