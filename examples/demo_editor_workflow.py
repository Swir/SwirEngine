from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.core.scene import Scene
from swirengine.editor_workflow import EditorWorkflow
from swirengine.graphics.primitives import Rectangle2D


with TemporaryDirectory() as temp_dir:
    scene = Scene()
    player = scene.add(Rectangle2D(16, 24, 32, 32, name="player"))
    workflow = EditorWorkflow(Path(temp_dir) / "demo_project", scene)

    workflow.save_scene("level_one")
    workflow.save_prefab("player", player)

    workflow.begin_playtest()
    player.x = 400
    scene.add(Rectangle2D(0, 0, 8, 8, name="runtime_spawn"))
    workflow.end_playtest()

    print("Scenes:", workflow.list_scenes())
    print("Prefabs:", workflow.list_prefabs())
    print("Restored player x:", scene.objects[0].x)
