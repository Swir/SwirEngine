# SwirEngine Roadmap

## 0.2 - Real 2D workflow — complete

Completed: textured sprites, alpha blending, texture cache, camera 2D, names/tags,
creator-friendly scene/input shortcuts, render layers, cached text rendering,
adjacent-texture GPU sprite batching and frame/render profiling.

## 0.3 - 2D gameplay systems — feature complete, hardening in progress

Completed: sprite sheets, named animation clips, asset manager, AABB box collisions,
collision layers/masks, one-shot keyboard and mouse input, tilemaps, JSON save data,
pooled particles, fixed-step arcade rigid-body physics, pluggable sound/music playback,
screen-space UI, labels, panels, buttons and progress bars.

Hardening completed so far: bounded dynamic-text cache, renderer statistics, frame profiler,
built-in debug overlay and sprite draw-call batching that preserves transparent render order.

Next: exercise 0.3.x with larger sample games, improve error messages/resource diagnostics and
stabilize the creator-facing API before moving to serious 3D.

## 0.4 - Serious 3D

Camera 3D, mesh abstraction, OBJ/glTF import, textures/materials, directional/point/spot
lights, skybox and post-processing.

## 0.5 - Architecture

Components/ECS, prefabs, serialization, scene files, hot reload and plugin API.

## 0.6 - Tools

Visual editor, hierarchy/inspector, asset browser, console/profiler and scene gizmos.

## 0.7+ - Runtime and export

Networking, packaging profiles, Windows/Linux/macOS exporters, Android/Web research targets.

## 1.0

Stable documented API with editor, 2D/3D rendering, physics, audio, assets, scene/prefab
workflow, tests and release tooling.
