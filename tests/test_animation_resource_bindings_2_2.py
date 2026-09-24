from __future__ import annotations

import json

import numpy as np
import pytest

from swirengine.editor_animation_resources22 import (
    AnimationPreviewResourceRefs22,
    animation_preview_resource_sidecar_path22,
)
from swirengine.editor_animation_state_machine22 import (
    AnimationMachineDocument22,
    AnimationStateNode22,
)
from swirengine.editor_animation_workspace22 import AnimationMachineWorkspace22
from swirengine.editor_animation_workspace_frontend22 import TkAnimationMachineEditorApp22
from swirengine.graphics.skeletal import (
    SkeletalAnimationChannel,
    SkeletalAnimationClip3D,
    Skeleton3D,
    SkeletonNode3D,
)


def _skeleton() -> Skeleton3D:
    return Skeleton3D((SkeletonNode3D(0, name="root"),))


def _clip(name: str) -> SkeletalAnimationClip3D:
    return SkeletalAnimationClip3D(
        name,
        (
            SkeletalAnimationChannel(
                node_index=0,
                path="translation",
                times=np.asarray([0.0, 1.0], dtype="f4"),
                values=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype="f4"),
            ),
        ),
    )


def _document() -> AnimationMachineDocument22:
    return AnimationMachineDocument22(
        states=(AnimationStateNode22("Idle", clip="idle"),),
        initial="Idle",
    )


def test_workspace_persists_and_resolves_creator_resource_refs(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.create("hero", _document())
    refs = workspace.configure_preview_resource_refs(
        "imports/hero.glb#skeleton",
        {"idle": "imports/hero.glb#clip:Idle"},
    )
    assert refs == AnimationPreviewResourceRefs22.from_mapping(
        "imports/hero.glb#skeleton",
        {"idle": "imports/hero.glb#clip:Idle"},
    )
    assert workspace.dirty is True
    workspace.save()
    assert workspace.dirty is False

    graph_path = workspace.store.path_for("hero")
    sidecar = animation_preview_resource_sidecar_path22(graph_path)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload == {
        "clips": {"idle": "imports/hero.glb#clip:Idle"},
        "format": "swir.animation-preview-resources.v1",
        "skeleton": "imports/hero.glb#skeleton",
    }

    reopened = AnimationMachineWorkspace22(tmp_path)
    reopened.open("hero")
    assert reopened.resource_refs == refs
    assert reopened.preview_bound is False
    assert reopened.validate_runtime() == (
        "preview resource references are configured but not resolved",
    )

    resources = {
        "imports/hero.glb#skeleton": _skeleton(),
        "imports/hero.glb#clip:Idle": _clip("idle"),
    }
    reopened.resolve_preview_resources(resources.__getitem__)
    assert reopened.preview_bound is True
    assert reopened.validate_runtime() == ()
    assert reopened.start_preview().preview_state == "Idle"


def test_switching_graph_drops_runtime_objects_and_resource_refs(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.create("hero", _document())
    workspace.configure_preview_resource_refs("hero-rig", {"idle": "hero-idle"})
    resources = {"hero-rig": _skeleton(), "hero-idle": _clip("idle")}
    workspace.resolve_preview_resources(resources.__getitem__)
    assert workspace.preview_bound is True

    workspace.create("enemy", _document())
    assert workspace.preview_bound is False
    assert workspace.resource_refs is None
    assert workspace.snapshot().resource_refs_configured is False


def test_legacy_graph_without_binding_sidecar_remains_openable(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.create("legacy", _document())
    workspace.save()

    reopened = AnimationMachineWorkspace22(tmp_path)
    reopened.open("legacy")
    assert reopened.resource_refs is None
    assert reopened.validate_runtime() == ("preview resources are not bound",)


def test_resource_resolver_rejects_wrong_runtime_type(tmp_path) -> None:
    workspace = AnimationMachineWorkspace22(tmp_path)
    workspace.create("hero", _document())
    workspace.configure_preview_resource_refs("hero-rig", {"idle": "hero-idle"})

    with pytest.raises(TypeError, match="Skeleton3D"):
        workspace.resolve_preview_resources(lambda _ref: object())


def test_editor_clip_ref_parser_is_deterministic_and_rejects_duplicates() -> None:
    assert TkAnimationMachineEditorApp22._parse_animation_clip_refs(
        "walk=hero#Walk, run=hero#Run"
    ) == {"walk": "hero#Walk", "run": "hero#Run"}

    with pytest.raises(ValueError, match="duplicate"):
        TkAnimationMachineEditorApp22._parse_animation_clip_refs("walk=a, walk=b")
    with pytest.raises(ValueError, match="id=resource"):
        TkAnimationMachineEditorApp22._parse_animation_clip_refs("walk")
