from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from swirengine import Scene
from swirengine.editor_authoring import EditorAuthoringSession, EditorAuthoringTransaction
from swirengine.editor import SceneInspector

TARGET_COUNT = 500
MAX_AUTHORING_SECONDS = 5.0


@dataclass
class WorkloadActor:
    name: str
    health: int = 100
    enabled: bool = True


def main() -> None:
    scene = Scene()
    actors = [scene.add(WorkloadActor(f"Actor-{index}")) for index in range(TARGET_COUNT)]
    inspector = SceneInspector(scene, history_limit=TARGET_COUNT + 10)
    authoring = EditorAuthoringSession(inspector)

    started = perf_counter()
    authoring.select(actors[0])
    for actor in actors[1:]:
        authoring.select(actor, mode="add")
    selection_seconds = perf_counter() - started

    started = perf_counter()
    result = authoring.set_property("health", 75)
    edit_seconds = perf_counter() - started

    assert authoring.selection_snapshot.count == TARGET_COUNT
    assert result.transaction.edit_count == TARGET_COUNT
    assert all(actor.health == 75 for actor in actors)

    started = perf_counter()
    undone = authoring.undo()
    undo_seconds = perf_counter() - started
    assert isinstance(undone, EditorAuthoringTransaction)
    assert all(actor.health == 100 for actor in actors)

    total_seconds = selection_seconds + edit_seconds + undo_seconds
    if total_seconds > MAX_AUTHORING_SECONDS:
        raise RuntimeError(
            f"editor authoring workload exceeded {MAX_AUTHORING_SECONDS:.1f}s: {total_seconds:.3f}s"
        )

    print(
        "editor-authoring-1.4 workload "
        f"targets={TARGET_COUNT} selection={selection_seconds:.4f}s "
        f"edit={edit_seconds:.4f}s undo={undo_seconds:.4f}s total={total_seconds:.4f}s"
    )


if __name__ == "__main__":
    main()
