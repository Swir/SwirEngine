from swirengine import PluginManager, Rectangle2D, Scene

scene = Scene()
scene.add(Rectangle2D(120, 80, 64, 64, name="player"))

plugins = PluginManager()
scene_state = plugins.state.domain("scene")
editor_state = plugins.state.domain("editor")

scene_state.register_scene("active-scene", scene)
selection = {"name": "player"}
editor_state.register(
    "selection",
    lambda: dict(selection),
    lambda value: (selection.clear(), selection.update(value)),
)

snapshot = plugins.state.capture(domains=("scene", "editor"))
scene.clear()
selection["name"] = "temporary"
plugins.state.restore(snapshot)

player = scene.find("player")
print("Restored:", player)
print("Selection:", selection)

# Module-backed plugins can preserve all domains or only editor-owned state:
# plugins.load_module("my_game_plugin", enable=True)
# plugins.reload("my_game_plugin")
# plugins.reload("my_game_plugin", state_domains=("scene", "editor"))
