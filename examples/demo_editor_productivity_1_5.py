from __future__ import annotations

from swirengine.editor15 import EditorBatchEditor, EditorCommandHistory, EditorPrefabDocument
from swirengine.graphics.primitives import Rectangle2D
from swirengine.prefab import Prefab


def main() -> None:
    source = Prefab(
        Rectangle2D(0, 0, 32, 32, name="body"),
        Rectangle2D(36, 0, 8, 8, name="sensor"),
        name="enemy",
    )
    history = EditorCommandHistory()
    document = EditorPrefabDocument(source, history=history)

    instance = document.instantiate()
    instance.objects[0].x = 96
    instance.objects[1].visible = False

    print("changes before apply:", document.diff(instance).changed_fields)
    document.apply(instance, selectors=["body"], properties=["x"])
    print("changes after selective apply:", document.diff(instance).changed_fields)

    variant = document.create_variant("enemy_stealth", instance)
    print("variant:", variant.name, "changes:", variant.changes.changed_fields)

    batch = EditorBatchEditor(history=history)
    plan = batch.preview(instance.objects, {"layer": 4}, label="Move enemy to layer 4")
    batch.commit(plan)
    print("batch fields:", plan.changed_fields, "history:", len(history.frame().undo))

    history.undo()
    print("undo restored layers:", [obj.layer for obj in instance.objects])


if __name__ == "__main__":
    main()
