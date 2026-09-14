# Editor workflow expansion

- Add a project-oriented `EditorWorkflow` over the existing stable scene, prefab, serialization and input APIs.
- Add deterministic `scenes/`, `prefabs/` and `settings/` project layout with safe project item names and discovery helpers.
- Add scene create/save/load flow plus prefab authoring, persistence, instantiation and overrides.
- Add editor-time semantic input binding persistence through the same `InputActions` profile used by games.
- Add reversible Play/Edit iteration: play mode snapshots authoring scene/input state and restores it when playtesting ends, with an explicit apply-back option.
- Add regression coverage, creator documentation and a runnable headless workflow example.

Release/PyPI remains frozen until the complete 1.1 roadmap reaches 10/10.
