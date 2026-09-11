# SwirEngine

**SwirEngine** is a Python-first 2D/3D game engine designed around one simple API for both dimensions.

Current milestone: **0.1.0 – Foundation**

Core goals:
- one API for 2D and 3D
- GPU rendering instead of a software-only drawing layer
- beginner-friendly Python API
- scene/entity architecture
- deterministic fixed updates
- keyboard and mouse input
- CLI project generator
- testable headless core
- future editor, physics, audio, networking and exporters

## Local install

```bash
python -m pip install -e ".[dev]"
pytest
```

## Quick 2D example

```python
from swirengine import Game, Rectangle2D, Color

game = Game("SwirEngine 2D", 1280, 720)
player = Rectangle2D(0, 0, 140, 80, Color(0.1, 0.7, 1.0, 1.0))
game.scene.add(player)

@game.update
def move(dt):
    speed = 400
    if game.input.key("A"):
        player.x -= speed * dt
    if game.input.key("D"):
        player.x += speed * dt

game.run()
```

## Quick 3D example

```python
from swirengine import Game, Cube3D, Color, Vec3

game = Game("SwirEngine 3D", 1280, 720, mode="3d")
cube = Cube3D(position=Vec3(0, 0, -4), color=Color(0.8, 0.2, 0.5, 1))
game.scene.add(cube)

@game.update
def spin(dt):
    cube.rotation.y += 45 * dt
    cube.rotation.x += 20 * dt

game.run()
```

## CLI

```bash
swirengine info
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
```

See `ROADMAP.md` for the planned path to 1.0.

## License

MIT
