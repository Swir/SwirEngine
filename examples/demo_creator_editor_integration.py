from __future__ import annotations

from swirengine import EditorFrontendController, EditorWorkspace, Scene
from swirengine.creator import CreatorEditorIntegration, EditorSystemRegistry
from swirengine.gameplay import Scheduler

scene = Scene()
workspace = EditorWorkspace(scene, project_name="SwirEngine 1.3 Creator Demo")
frontend = EditorFrontendController(workspace)

scheduler = Scheduler()
scheduler.call_every(0.5, lambda: None)

systems = EditorSystemRegistry()
systems.register("gameplay", scheduler, title="Gameplay Runtime", category="gameplay")
systems.register(
    "renderer-2d",
    {
        "render_roots": 12,
        "objects_culled": 104,
        "tilemap_candidates": 943,
    },
    title="2D Renderer",
    category="rendering",
)
systems.register(
    "large-world",
    {
        "tracked_chunks": 37,
        "active_chunks": 9,
        "provider_queries": 0,
    },
    title="Large World",
    category="world",
)

creator = CreatorEditorIntegration(frontend, systems=systems)
frame = creator.frame()

print(frame.frontend.shell.project_name)
for system in frame.systems.systems:
    metrics = ", ".join(f"{metric.name}={metric.display_value}" for metric in system.metrics)
    print(f"[{system.category}] {system.title}: {metrics}")

creator.set_system_filter(category="rendering")
filtered = creator.frame()
print("filtered:", [system.system_id for system in filtered.systems.systems])
