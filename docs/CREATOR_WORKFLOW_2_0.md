# SwirEngine 2.0 Creator Workflow & Integrated Tooling

SwirEngine 2.0 Milestone 2 turns the existing project-production systems into one creator-facing
inspection and preparation path. It does not replace the established scene, prefab, input, save,
content or export APIs; it composes them so a project can be checked before the creator starts a
runtime session or build.

## Start a project

```bash
swirengine new MyGame --mode 2d
cd MyGame
```

New projects now include the directories and editable defaults used by the integrated workflow:

- `assets/`
- `scenes/`
- `prefabs/`
- `scripts/`
- `settings/`
- `config/controls.json`
- `config/settings.json`

The generated project keeps the public 1.x engine constraint while the repository develops 2.0.
The package/module version remains 1.5.0 until the final verified 2.0 release gate.

## Inspect the complete creator contract

```bash
swirengine workflow .
```

The command checks the project manifest, deterministic run plan, optional scene/prefab registry,
optional production content graph, shipping input/settings defaults, editor directories and the
desktop save/profile location policy. It does not launch the game, write save data or export a build.

Validate one declared export profile at the same time:

```bash
swirengine workflow . --profile windows
```

For tooling and CI, request stable JSON:

```bash
swirengine workflow . --profile linux --json
```

A blocked report exits with status `2`. Every reported error includes an actionable next step rather
than requiring the creator to infer the fix from a traceback.

## Prepare an existing project

```bash
swirengine workflow . --prepare
```

Preparation is additive and idempotent. It creates only missing creator directories and missing
editable input/settings defaults. Existing files are never overwritten.

Scene or prefab document decoding can be skipped for fast metadata-only inspection while path and
dependency checks remain active:

```bash
swirengine workflow . --skip-document-validation
```

## Continue with existing production commands

Once the workflow report is ready, use the established commands without switching project formats:

```bash
swirengine run . --dry-run
swirengine run .
swirengine export . --profile windows
```

Scene/prefab authoring continues through `EditorWorkflow`, production scene packages continue through
`ScenePackageRegistry`, content preparation continues through `ContentBuildGraph`, player settings
continue through the shipping settings contract, and save/profile data remains outside redistributable
project content through the production user-data policy.

## Data boundaries

`swirengine workflow` reports the platform and policy source for player data but does not create a
save directory. Project defaults under `config/` are redistributable project content; player overrides
and save/profile data remain in the platform-specific user-data tree.

The report fingerprint intentionally excludes absolute checkout and user-data paths. Two equivalent
project checkouts therefore produce the same workflow fingerprint when their portable configuration
and diagnostics are identical.

## Real-game verification

The dedicated `tools/verify_creator_workflow_2_0.py` gate wraps the maintained 2D and 3D real-game
fixtures in production manifests and proves that one workflow inspection reaches their run plan,
scene packages, content graph and editable shipping defaults without manual file surgery.

Milestone completion still requires exact-head CI. The existence of this workflow or document alone
does not advance roadmap progress.
