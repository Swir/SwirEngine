from __future__ import annotations

from swirengine import Scene, editor14
from swirengine.editor import SceneInspector


def test_editor14_public_exports_are_unique_and_resolvable() -> None:
    assert len(editor14.__all__) == len(set(editor14.__all__))
    for name in editor14.__all__:
        assert hasattr(editor14, name), name


def test_editor14_facade_builds_authoring_runtime_and_specialized_layers() -> None:
    scene = Scene()
    inspector = SceneInspector(scene)
    authoring = editor14.EditorAuthoringSession(inspector)
    runtime = editor14.EditorRuntimeSession(scene)
    play = editor14.EditorAuthoringPlayController(authoring, runtime)
    specialized = editor14.EditorSpecializedInspectors(authoring)

    assert play.authoring is authoring
    assert play.runtime is runtime
    assert specialized.authoring is authoring
    assert editor14.EDITOR_AUTHORING_FORMAT == "swirengine.editor_authoring"
    assert editor14.EDITOR_AUTHORING_VERSION == 1
