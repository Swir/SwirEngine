from dataclasses import dataclass

from swirengine import (
    AssetManager,
    EditorAssetBrowser,
    EditorConsole,
    EditorFrontendController,
    EditorProfiler,
    EditorWorkspace,
    Profiler,
    Scene,
    TkEditorApp,
)


@dataclass
class Player:
    name: str = "Player"
    enabled: bool = True
    health: int = 100
    speed: float = 5.0


scene = Scene()
player = scene.add(Player())
workspace = EditorWorkspace(scene, project_name="Visual Editor Demo", asset_root="assets")
workspace.select(player)

assets = EditorAssetBrowser(AssetManager("assets"))
console = EditorConsole()
console.write("Visual editor demo ready", source="demo")
profiler = EditorProfiler(Profiler())

controller = EditorFrontendController(
    workspace,
    asset_browser=assets,
    console=console,
    profiler=profiler,
)
TkEditorApp(controller).run()
