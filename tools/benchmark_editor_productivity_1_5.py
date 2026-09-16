from __future__ import annotations

import time

from swirengine.editor15 import EditorBatchEditor, EditorPrefabDocument
from swirengine.graphics.primitives import Rectangle2D
from swirengine.prefab import Prefab

OBJECTS = 120
ITERATIONS = 200
BUDGET_SECONDS = 5.0


def main() -> None:
    source = Prefab(
        *(
            Rectangle2D(float(index), 0.0, 8.0, 8.0, name=f"item-{index}")
            for index in range(OBJECTS)
        ),
        name="benchmark",
    )
    document = EditorPrefabDocument(source)
    instance = document.instantiate()
    batch = EditorBatchEditor()

    started = time.perf_counter()
    for step in range(ITERATIONS):
        index = step % OBJECTS
        instance.objects[index].x = float(step + 1000)
        document.diff(instance)
        document.apply(instance, selectors=[index], properties=["x"])
        if step % 5 == 0:
            plan = batch.preview(
                instance.objects[:24],
                {"layer": step % 7},
                label="benchmark batch",
            )
            batch.commit(plan)
    elapsed = time.perf_counter() - started

    if document.diff(instance).changed_fields:
        raise RuntimeError("benchmark ended with unapplied prefab changes")
    print(
        f"editor-productivity workload: {OBJECTS} objects, "
        f"{ITERATIONS} iterations in {elapsed:.3f}s "
        f"(budget {BUDGET_SECONDS:.1f}s)"
    )
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"editor-productivity benchmark exceeded {BUDGET_SECONDS:.1f}s budget"
        )


if __name__ == "__main__":
    main()
