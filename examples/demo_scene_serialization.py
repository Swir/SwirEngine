from pathlib import Path

from swirengine import Color, Rectangle2D, Scene, SceneSerializer, Sprite2D

scene = Scene()
scene.add(Rectangle2D(320, 180, 280, 120, color=Color(0.08, 0.16, 0.3), name="panel"))
scene.add(Sprite2D("assets/hero.png", x=320, y=180, name="hero", tags={"player"}))

serializer = SceneSerializer()
path = serializer.dump_scene(scene, Path("example_level.swirscene"))
restored = serializer.load_scene(path)

print(f"Saved {len(scene)} objects to {path}")
print(f"Reloaded: {[getattr(obj, 'name', '') for obj in restored]}")
