from swirengine import PluginManager, Rectangle2D, Scene

scene = Scene()
scene.add(Rectangle2D(120, 80, 64, 64, name="player"))

plugins = PluginManager()
plugins.state.register_scene("active-scene", scene)

snapshot = plugins.state.capture()
scene.clear()
plugins.state.restore(snapshot)

player = scene.find("player")
print("Restored:", player)

# Module-backed plugins use the same registry automatically:
# plugins.load_module("my_game_plugin", enable=True)
# plugins.reload("my_game_plugin")  # scene/tool state is captured and restored
