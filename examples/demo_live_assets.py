from pathlib import Path

from swirengine import AssetManager

assets = AssetManager("assets")
assets.register("settings", "settings.txt")
assets.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))

settings_path = assets.resolve("settings")
settings_path.parent.mkdir(parents=True, exist_ok=True)
if not settings_path.exists():
    settings_path.write_text("quality=high\n", encoding="utf-8")

assets.watch("settings")
print("Loaded:", assets.load("settings").strip())
print("Edit", Path(settings_path), "then call poll_changes() from your editor/game update loop.")

for result in assets.poll_changes():
    print(result)
