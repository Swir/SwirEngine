import swirengine
manager = swirengine.PluginManager()
manager.load_module("my_game_plugin", enable=True)

reloader = swirengine.PluginAutoReloader(manager)
reloader.watch("my_game_plugin", "my_game_plugin.py")

print("Watching my_game_plugin.py. Save the file to trigger a state-preserving reload.")
while True:
    for result in reloader.poll():
        if result.reloaded:
            print(f"Reloaded {result.plugin}: {result.path}")
        else:
            print(f"Reload failed for {result.plugin}: {result.error}")
