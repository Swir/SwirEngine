# SwirEngine 0.2.0

SwirEngine is a Python-first 2D/3D game engine built around one approachable API.
The goal is simple: let people make real games in Python without making them learn
OpenGL before they can put a character on screen.

## What works now

- one `Game` API for 2D and 3D
- GPU rendering with ModernGL / OpenGL 3.3
- GLFW window, keyboard and mouse input
- colored 2D primitives
- **textured `Sprite2D` rendering with alpha blending**
- **lazy texture cache**
- **movable/zoomable `Camera2D`**
- lit 3D cubes
- scene lifecycle, names and tags
- `game.add(...)`, `game.spawn(...)`, `game.remove(...)` convenience API
- `game.key("W")` input shorthand
- variable update + deterministic fixed-update loop
- vectors, colors and transforms
- CLI project generator
- tests + multi-platform GitHub Actions CI

## Install for development

```bash
python -m pip install -e ".[dev]"
pytest
```

## Tiny 2D game

```python
from swirengine import Game, Sprite2D

game = Game("My Game")
player = game.add(Sprite2D("player.png", name="player"))

@game.update
def update(dt):
    speed = 300
    if game.key("A"):
        player.x -= speed * dt
    if game.key("D"):
        player.x += speed * dt

    game.camera.follow(player)

game.run()
```

When width/height are omitted, a sprite uses the source image dimensions. You can
resize it directly:

```python
player.width = 128
player.height = 128
```

`Color` is immutable, so tint replacement is explicit:

```python
from swirengine import Color
player.tint = Color(1.0, 1.0, 1.0, 0.8)
```

## Find objects without keeping every variable

```python
player = game.scene.find("player")
actors = game.scene.tagged("actor")
```

## Tiny 3D game

```python
from swirengine import Color, Cube3D, Game, Vec3

game = Game("My 3D Game", mode="3d")
cube = game.add(Cube3D(position=Vec3(0, 0, -4), color=Color(0.8, 0.2, 0.5, 1)))

@game.update
def spin(dt):
    cube.rotation.y += 45 * dt

game.run()
```

## CLI

```bash
swirengine info
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
```

See `ROADMAP.md` for the path to the stable 1.0 SDK and visual editor.
