# Changelog

## 0.4.16 - 2026-09-12

Automatic plugin file-watching and development hot-reload workflow update.

- added public `PollingFileWatcher`, `FileChangeEvent`, `PluginAutoReloader` and `ReloadResult` APIs
- added dependency-free deterministic polling for file creation, modification and deletion across Windows, Linux and macOS
- added source-file-to-plugin mappings that automatically call `PluginManager.reload(...)` after edits
- preserve registered runtime state by default during watcher-triggered reloads, building on the 0.4.15 scene/ECS snapshot pipeline
- report reload success/failure as structured results and optional callbacks instead of crashing the editor/game polling loop
- keep deleted files watched so recreating a source file can trigger a later reload
- added regression coverage for watcher lifecycle and automatic plugin reload behavior
- added a runnable automatic-reload example and advanced the 0.5 roadmap toward editor-owned state domains and live asset reload
- bumped package version to 0.4.16

## 0.4.15 - 2026-09-12

State-preserving plugin hot-reload architecture update.

- added public `HotReloadStateRegistry`, `HotReloadSnapshot` and `HotReloadStateError` APIs
- added deterministic named runtime-state providers with ordered capture/restore snapshots
- added partial snapshots, explicit provider removal/replacement and strict missing-provider diagnostics
- added `register_scene(...)` bridging versioned `SceneSerializer` snapshots into the hot-reload pipeline while preserving the same live `Scene` object
- made module-backed `PluginManager.reload(...)` automatically preserve registered runtime state by default
- added `preserve_state=False` for advanced reloads that intentionally discard runtime state
- strengthened reload rollback so failed replacement lifecycle/state restoration cleans up the replacement, restores the previous plugin and reapplies the captured state
- centralized replacement dependency validation so hot reload rejects malformed/self/empty dependencies consistently with initial registration
- clear hot-reload state providers during manager shutdown to avoid stale editor/runtime callbacks
- added regression coverage for ordered/partial snapshots, capture errors, scene restoration, successful stateful reload, rollback and opt-out behavior
- added a runnable hot-reload-state example and advanced the 0.5 architecture roadmap toward watcher-driven reload/editor state domains
- bumped package version to 0.4.15

## 0.4.14 - 2026-09-12

ECS reference-graph persistence update.

- upgraded scene/prefab documents to format version 3 with automatic v1/v2 migration
- added stable `$entity` references from registered ECS components to persisted entities
- added deterministic `$component` references between persisted ECS components
- restore cyclic component graphs by allocating every entity/component shell before field hydration
- preserved existing component-to-scene-object `$ref` behavior and legacy document compatibility
- added strict validation for malformed or unknown entity/component references
- expanded ECS persistence regression coverage for cyclic graphs, invalid references and v1/v2 migration
- expanded the persistence example to demonstrate entity and component references
- advanced the 0.5 architecture roadmap toward deeper scene/editor hot reload
- bumped package version to 0.4.14

## 0.4.13 - 2026-09-12

Plugin runtime and hot-reload architecture update.

- added public `PluginManager`, `PluginInfo` and `PluginError` APIs
- added deterministic plugin registration plus `on_load`, `on_enable`, `on_disable` and `on_unload` lifecycle hooks
- added dependency-aware activation with recursive dependency enablement, missing-dependency diagnostics and cycle detection
- prevented disabling required plugins unless cascade shutdown is explicitly requested
- added named shared-service publishing so plugins can collaborate without direct import coupling
- added module plugin entrypoints through `create_plugin()` or `plugin`
- added controlled module hot reload that preserves enabled state and attempts rollback when replacement lifecycle setup fails

