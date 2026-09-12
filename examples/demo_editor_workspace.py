from dataclasses import dataclass

from swirengine import EditorProjectState, EditorWorkspace, Scene


@dataclass
class Actor:
    name: str
    health: int = 100


scene = Scene()
player = scene.add(Actor("Player"))
camera_anchor = scene.add(Actor("Camera Anchor"))

workspace = EditorWorkspace(scene, scene_id="levels/main", project_name="Workspace Demo")
workspace.inspector.set_parent(camera_anchor, player)
workspace.select(player)
workspace.inspector.set_property("health", 80)
workspace.configure_viewport(mode="2d", snap_enabled=True, translation_snap=16.0)
workspace.configure_panel("profiler", visible=True)

frame = workspace.frame()
print("hierarchy:", [(row.label, row.depth) for row in frame.hierarchy])
print("selected:", None if frame.inspector is None else frame.inspector.type_name)
print("undo available:", frame.can_undo)

project = workspace.capture_project()
serialized = project.dumps()
restored = EditorProjectState.loads(serialized)
print("project scenes:", [state.scene_id for state in restored.scenes])
