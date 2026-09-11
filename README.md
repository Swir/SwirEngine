# SwirEngine 0.4.5

SwirEngine is a Python-first 2D/3D game engine built around one approachable API.
Its goal is to let people create real games in Python without learning OpenGL before
they can put a character or 3D model on screen.

> SwirEngine is still pre-1.0. The public API is growing quickly, but the project is
> already being kept testable and cross-platform from the start.

## What works now

- one `Game` API for 2D and 3D
- GPU rendering with ModernGL / OpenGL 3.3
- GLFW keyboard + mouse input with held/pressed/released queries
- colored 2D primitives, render layers and camera-independent screen-space objects
- textured `Sprite2D` rendering with alpha blending
- adjacent compatible sprite batching to reduce draw calls without changing render order
- renderer statistics for draw calls, batches, sprites, meshes, triangles and cache usage
- frame profiler with update/physics/render timings and history averages
- built-in live debug overlay through `game.show_debug()`
- bounded LRU text-texture cache for changing HUD/debug text
- cached `Text2D` rendering with custom fonts/sizes/colors
- built-in UI labels, panels, buttons and progress bars
- sprite-sheet UV regions and named `AnimatedSprite2D` animations
- reusable `TileMap2D` grids backed by pooled sprites
- lazy GPU texture cache
- movable/zoomable `Camera2D`
- real perspective `Camera3D` with look-at and local-space movement
- reusable `MeshData` / `Mesh3D` geometry with lazy GPU mesh caching
- Wavefront OBJ plus static glTF/GLB mesh and scene import
- material-aware glTF/GLB base-color texture loading
- `DirectionalLight3D`, `PointLight3D` and `SpotLight3D`
- distance and spotlight-cone attenuation plus Phong specular/shininess materials
- project `AssetManager` with aliases and strict validation
- sound effects and background music through a pluggable audio service
- AABB collision detection plus fixed-step arcade rigid-body physics
- pooled particle effects
- JSON `SaveStore` with atomic persistence
- scene lifecycle, names and tags
- creator-friendly factories for gameplay, UI and 3D objects
- variable update + deterministic fixed-update loop
- vectors, colors and transforms
- CLI project generator
- tests + multi-platform GitHub Actions CI

## Install for development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples
python -m compileall -q src examples
```

Audio playback is optional so headless development remains lightweight:

```bash
python -m pip install -e ".[audio]"
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

## Performance profiler and debug overlay

Enable the built-in diagnostics HUD before `game.run()`:

```python
from swirengine import Game

game = Game("Profile Me")
game.show_debug()
game.run()
```

The overlay displays FPS, frame/CPU time, update/physics/render timings, draw calls,
sprite count, sprite batches and triangle count. Programmatic data is available through
`game.profiler.latest`, `game.profiler.samples` and `game.profiler.average(...)`.

The 2D renderer automatically merges adjacent sprites that share the same texture, layer
and screen/world-space mode into a single GPU draw call. Batching deliberately preserves
render order, which keeps alpha-blended scenes predictable.

## UI and text

UI elements are screen-space objects, so they stay fixed while the world camera moves.
Buttons include hover, press and click handling, and overlapping buttons only activate the
topmost control.

```python
from swirengine import Game

game = Game("Menu")
game.panel(0, 0, 420, 260)
game.label("Main Menu", 0, 85, font_size=32)
progress = game.progress_bar(0, 20, 280, 24, value=0.4)


def play(_button):
    progress.value = min(1.0, progress.value + 0.1)


game.button("Play", 0, -70, 180, 52, on_click=play)
game.run()
```

Use `game.text(...)` for world-space text that follows the camera, and `game.label(...)`
for HUD/menu text. `Text2D` supports a custom TrueType font path, size, color and scale.
Dynamic text textures are kept in a bounded LRU cache so changing counters/debug labels do
not grow GPU memory forever.

## Audio and music

Put supported audio files under `assets/`, install the audio extra, then use the same
asset resolution rules as sprites and tilemaps:

```python
from swirengine import Game

game = Game("Audio Demo")
game.audio.master_volume = 0.8
game.audio.music_volume = 0.6
music = game.music("music/theme.ogg")

@game.update
def update(_dt):
    if game.key_pressed("SPACE"):
        shot = game.sound("sfx/laser.wav", volume=0.7)
        shot.set_volume(0.9)
    if game.key_pressed("M"):
        music.stop()

game.run()
```

`Game.music(...)` replaces the previous music track and loops by default. Sound effects can
loop independently. `AudioHandle` exposes `stop()`, `set_volume(...)`, `active`, `loop` and
`path`. The backend protocol is public, so future platform targets can provide another
implementation without changing game code.

## Tilemaps

A tile atlas is addressed row-major from its top-left tile. The tilemap owns a fixed pool
of sprites, so editing cells does not continuously allocate scene objects. Because pooled
tiles usually share one atlas texture, they also benefit strongly from sprite batching.

```python
from swirengine import Game

game = Game("Tile World")
world = game.tilemap(
    "tiles.png",
    width=20,
    height=12,
    tile_width=32,
    tile_height=32,
    atlas_columns=8,
    atlas_rows=4,
    layer=-10,
)

world.fill(0)
world.set_tile(3, 2, 7)
world.set_tile(4, 2, 7)
world.set_tile(5, 2, None)

game.run()
```

Use `world.world_to_cell(x, y)` for picking and `world.cell_to_world(column, row)` when
placing actors on grid centers.

## Save data

Pass `save_path` to autoload an existing JSON save file. Writes are atomic.

```python
from swirengine import Game

game = Game("Persistent Game", save_path="saves/profile.json")
score = game.storage.get("score", 0)
game.storage.set("score", score + 100).save()
```

`SaveStore` can also be used directly when a game needs multiple save slots.

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

## Collision and physics

```python
from swirengine import Color, Game, Rectangle2D

game = Game("Physics")
player = game.add(Rectangle2D(0, 0, 64, 64, Color(0.2, 0.7, 1.0, 1.0)))
body = game.rigidbody(player, restitution=0.1)
body.apply_impulse(220, 420)

game.run()
```

The collision layer also supports lightweight AABB queries when full rigid-body response
is unnecessary.

## Asset aliases

```python
game.assets.register("hero", "characters/hero.png")
hero_path = game.assets.require("hero")
```

Aliases work for audio too, because the audio service shares the game's `AssetManager`.

## 3D camera, meshes and import

`Game(mode="3d")` creates a `Camera3D`. Its default view looks down the negative Z axis,
so older `Cube3D` scenes remain compatible. You can move in camera-local axes and point it
at any world position:

```python
from swirengine import Color, Cube3D, Game, Vec3

game = Game("My 3D Game", mode="3d")
cube = game.add(Cube3D(position=Vec3(0, 0, -4), color=Color(0.8, 0.2, 0.5, 1)))
game.camera.move(0, 1, 2).look_at(cube.position)

@game.update
def spin(dt):
    cube.rotation.y += 45 * dt

game.run()
```

For imported geometry, put an OBJ, glTF or GLB asset below `assets/`. OBJ files can be
loaded with `game.obj(...)`, while static glTF meshes can be loaded with `game.gltf(...)`.
Lower-level glTF APIs preserve scene hierarchies and per-primitive materials when needed.

## 3D lighting and materials

Explicit lights are scene objects and can be created directly from `Game`. When a scene
contains no explicit light, the renderer keeps the historical default directional light so
older 3D projects continue to render as expected.

```python
from swirengine import Color, Game, Material3D, Vec3, cube_mesh

game = Game("Lighting", mode="3d")
material = Material3D(
    tint=Color(0.6, 0.8, 1.0, 1.0),
    ambient=0.12,
    diffuse=0.8,
    specular=0.6,
    shininess=48.0,
)
model = game.mesh(cube_mesh(), material=material)
model.position = Vec3(0.0, 0.0, -4.0)

game.directional_light(direction=Vec3(-0.4, -1.0, -0.3), intensity=0.7)
game.point_light(position=Vec3(2.0, 2.0, -2.0), range=8.0, intensity=2.0)
game.spot_light(
    position=Vec3(-2.0, 3.0, -1.0),
    direction=Vec3(0.5, -0.8, -0.4),
    inner_angle=18.0,
    outer_angle=30.0,
)

game.camera.look_at(model.position)
game.run()
```

`DirectionalLight3D` models distant sun/moon lighting. `PointLight3D` uses smooth distance
attenuation, while `SpotLight3D` combines distance attenuation with smooth inner/outer cone
cutoffs. The current 0.4 renderer accepts one active light of each type; multiple lights per
type, richer PBR mapping, shadows, skyboxes and post-processing remain roadmap work.

## CLI

```bash
swirengine info
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
```

See `ROADMAP.md` for the path to the stable 1.0 SDK and visual editor.
