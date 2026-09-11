# Changelog

## 0.3.1 - 2026-09-11

Level-building and persistence update.

- added `TileMap2D` with atlas UV mapping and a fixed reusable sprite pool
- added tile fill/clear/row loading plus world/cell coordinate helpers
- added `Game.tilemap(...)` with asset-root resolution and automatic scene registration
- added tilemap child cleanup through `Game.remove(...)`
- added `SaveStore` with defaults, dict-like helpers and UTF-8 JSON persistence
- added atomic save writes using a same-directory temporary file and `os.replace`
- added optional `Game.storage` autoload through `save_path=...`
- added tilemap and save-data tests
- bumped package version to 0.3.1

## 0.3.0 - 2026-09-11

First gameplay-systems milestone.

- added `SpriteSheet`, `AnimationClip` and `AnimatedSprite2D`
- added normalized sprite UV regions for sprite-sheet rendering
- added stable 2D render layers
- added `AssetManager` with aliases, resolution, existence checks and strict loading
- added `AABB`, `BoxCollider2D` and `CollisionWorld2D`
- added collision layers/masks and tag-filtered collision queries
- added `Game.sprite(...)` and `Game.collider(...)` convenience factories
- added collider cleanup when a scene object is removed through `Game.remove(...)`
- added named key pressed/released helpers
- fixed all lint failures found by GitHub Actions after 0.2.0
- upgraded CI to current Node-24-based official GitHub actions
- disabled matrix fail-fast so one platform cannot hide results from the others
- expanded the suite from 16 to 33 tests
- added animation and collision examples

## 0.2.0 - 2026-09-11

First creator-focused 2D milestone.

- added `Sprite2D` with PNG/JPEG/etc. loading through Pillow
- added GPU texture rendering, alpha blending and lazy texture cache
- added `Camera2D` with movement, zoom, look-at and follow helpers
- added `Game.add`, `spawn`, `add_many`, `remove` and `key` shortcuts
- added scene names, tags, lookup helpers and collection protocol support
- added visibility flags for renderable primitives
- added renderer resource cleanup
- made plain `pytest` work directly from a source checkout
- expanded tests and 2D examples

## 0.1.0 - 2026-09-11

Initial engine foundation.

- unified `Game` API with 2D and 3D modes
- OpenGL 3.3 renderer via ModernGL
- GLFW window/input backend
- 2D colored rectangle rendering
- lit 3D cube rendering
- scene lifecycle
- event bus
- keyboard and mouse state
- variable and fixed update callbacks
- vector/color/transform math
- CLI project generator
- examples and tests
- GitHub Actions CI
