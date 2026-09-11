# SwirEngine 0.3.0

SwirEngine is a Python-first 2D/3D game engine built around one approachable API.
Its goal is to let people create real games in Python without learning OpenGL before
they can put a character on screen.

> SwirEngine is still pre-1.0. The public API is growing quickly, but the project is
> already being kept testable and cross-platform from the start.

## What works now

- one `Game` API for 2D and 3D
- GPU rendering with ModernGL / OpenGL 3.3
- GLFW window, keyboard and mouse input
- colored 2D primitives and render layers
- textured `Sprite2D` rendering with alpha blending
- sprite-sheet UV regions and named `AnimatedSprite2D` animations
- lazy GPU texture cache
- movable/zoomable `Camera2D`
- project `AssetManager` with aliases and strict validation
- AABB / box collision detection and `CollisionWorld2D`
- lit 3D cubes
- scene lifecycle, names and tags
- `game.add(...)`, `game.spawn(...)`, `game.remove(...)` creator shortcuts
- `game.sprite(...)` and `game.collider(...)` factories
- held / pressed / released keyboard queries
- variable update + deterministic fixed-update loop
- vectors, colors and transforms
- CLI project generator
- tests + multi-platform GitHub Actions CI

## Install for development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples
```

## Tiny 2D game

Put `player.png` in `assets/`, then:

```python
from swirengine import Game

game = Game("My Game")
player = game.sprite("player.png", x=0, y=0, width=96, height=96, name="player")

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

## Sprite-sheet animation

```python
from swirengine import AnimatedSprite2D, Game, SpriteSheet

game = Game("Animated Hero")
sheet = SpriteSheet(columns=6, rows=2)
hero = AnimatedSprite2D(game.assets.resolve("hero_sheet.png"), width=96, height=96)
hero.add_animation("idle", sheet.row(0), fps=6)
hero.add_animation("walk", sheet.row(1), fps=12)
game.add(hero)

@game.update
def update(dt):
    moving = game.key("A") or game.key("D")
    hero.play("walk" if moving else "idle")

game.run()
```

Animations advance automatically because `AnimatedSprite2D` participates in normal scene
updates. Clips can loop or stop on their final frame.

## Collision in a few lines

```python
from swirengine import Color, Game, Rectangle2D

game = Game("Collision")
player = game.add(Rectangle2D(0, 0, 64, 64, Color(0.2, 0.7, 1.0, 1.0)))
wall = game.add(Rectangle2D(200, 0, 64, 240, Color(1.0, 0.3, 0.3, 1.0)))
player_hitbox = game.collider(player, tag="player")
game.collider(wall, tag="wall")

@game.update
def update(dt):
    old_x = player.x
    if game.key("D"):
        player.x += 250 * dt
    if game.collisions.query(player_hitbox, tag="wall"):
        player.x = old_x

game.run()
```

The current collision system is intentionally lightweight: it provides AABB detection,
layers/masks and queries. Rigid-body physics and collision response belong to a later
milestone.

## Asset aliases

```python
game.assets.register("hero", "characters/hero.png")
hero_path = game.assets.require("hero")
```

`require()` fails immediately if an asset is missing, which is useful for validation and
build tooling.

## One-shot input

```python
if game.key_pressed("SPACE"):
    shoot()

if game.key_released("ESCAPE"):
    close_menu()
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
