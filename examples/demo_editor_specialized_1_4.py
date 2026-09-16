from __future__ import annotations

from dataclasses import dataclass

from swirengine import BoxCollider2D, Material3D, Mesh3D, RigidBody2D, Scene, cube_mesh
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession
from swirengine.editor_specialized import EditorSpecializedInspectors


@dataclass
class BodyTarget:
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0


def main() -> None:
    scene = Scene()
    mesh_a = scene.add(
        Mesh3D(cube_mesh(), material=Material3D(metallic=0.2, roughness=0.3), name="Metal A")
    )
    mesh_b = scene.add(Mesh3D(cube_mesh(), material=None, name="Metal B"))

    authoring = EditorAuthoringSession(SceneInspector(scene))
    specialized = EditorSpecializedInspectors(authoring)
    authoring.select(mesh_a)
    authoring.select(mesh_b, mode="add")

    material = specialized.inspect("material")
    print(
        "material:",
        f"targets={len(material.target_keys)}",
        f"roughness_mixed={material.field('roughness').mixed}",
    )
    result = specialized.set_property("material", "roughness", 0.6)
    print("material edit:", f"history_edits={result.transaction.edit_count}")

    scene2 = Scene()
    target_a = BodyTarget()
    target_b = BodyTarget()
    body_a = RigidBody2D(target_a, BoxCollider2D(target_a), mass=1.0)
    body_b = RigidBody2D(target_b, BoxCollider2D(target_b), mass=3.0)
    entity_a = scene2.create_entity(name="Body A")
    entity_b = scene2.create_entity(name="Body B")
    entity_a.add(body_a)
    entity_b.add(body_b)

    authoring2 = EditorAuthoringSession(SceneInspector(scene2))
    specialized2 = EditorSpecializedInspectors(authoring2)
    authoring2.select(entity_a)
    authoring2.select(entity_b, mode="add")
    physics = specialized2.set_property("physics", "mass", 2.0)
    print(
        "physics edit:",
        f"targets={len(physics.target_keys)}",
        f"history_edits={physics.transaction.edit_count}",
        f"masses={(body_a.mass, body_b.mass)}",
    )
    authoring2.undo()
    print("physics undo:", f"masses={(body_a.mass, body_b.mass)}")


if __name__ == "__main__":
    main()
