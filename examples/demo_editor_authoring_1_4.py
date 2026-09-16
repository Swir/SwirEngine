from __future__ import annotations

from pathlib import Path

from swirengine import Cube3D, Scene, Sprite2D, Vec3
from swirengine.editor_assets import EditorAssetDragPayload
from swirengine.editor_authoring_workspace import EditorAuthoringWorkspace


def main() -> None:
    scene = Scene()
    hero = scene.add(Sprite2D("textures/hero_old.png", name="Hero"))
    shadow = scene.add(Sprite2D(Path("textures/shadow_old.png"), name="Shadow"))
    left = scene.add(Cube3D(position=Vec3(-2.0, 0.0, -5.0), name="LeftCube"))
    right = scene.add(Cube3D(position=Vec3(2.0, 0.0, -5.0), name="RightCube"))
    workspace = EditorAuthoringWorkspace(scene, project_name="Authoring 1.4 Demo")

    workspace.select(hero)
    workspace.select(shadow, mode="add")
    texture = EditorAssetDragPayload(
        "textures/neon_grid.png",
        "neon_grid.png",
        "image",
        ".png",
    )
    drop = workspace.drop_asset_on_selected_property(texture, "texture")
    assert drop.transaction.edit_count == 2
    assert hero.texture == "textures/neon_grid.png"
    assert shadow.texture == Path("textures/neon_grid.png")

    workspace.undo()
    assert hero.texture == "textures/hero_old.png"
    assert shadow.texture == Path("textures/shadow_old.png")
    workspace.redo()

    workspace.select(left)
    workspace.select(right, mode="add")
    workspace.configure_viewport(snap_enabled=True, translation_snap=1.0)
    move = workspace.apply_selected_gizmo("translate", "y", 1.4)
    assert move.transaction.edit_count == 2
    assert left.position.y == 1.0
    assert right.position.y == 1.0

    print("SwirEngine 1.4 editor authoring demo: OK")
    print(f"asset drop targets={len(drop.target_keys)} path={drop.relative_path}")
    print(f"gizmo targets={len(move.results)} selection={workspace.selection.count}")


if __name__ == "__main__":
    main()
