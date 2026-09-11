# Changelog

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
